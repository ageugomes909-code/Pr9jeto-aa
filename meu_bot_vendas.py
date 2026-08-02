import discord
from discord import app_commands
import asyncio
from datetime import datetime
from flask import Flask
from threading import Thread
import os

# --- SISTEMA DE WEB SERVER PARA O RENDER NÃO CAIR ---

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def manter_online():
    t = Thread(target=run)
    t.start()

# --- CÓDIGO DO BOT ---

TOKEN_BOT = os.getenv("DISCORD_TOKEN")

class MeuBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):  
        await self.tree.sync()

bot = MeuBot()

# --- BANCO DE DADOS EM MEMÓRIA ---

donos_permitidos = [1410272734012772524]
status_sistema = "normal"
canal_logs_id = None
canal_aprovadas_id = None

paineis_produtos = {}  
carrinhos_aguardando_pix = {}
dados_carrinhos = {}   
carrinhos_aprovados = set()
carrinhos_ativos_alerta = set()

historico_vendas = []  

canal_anuncio_id = None
texto_anuncio_auto = None
msg_anuncio_anterior = None

# DICIONÁRIO DE TEXTOS DO SISTEMA
mensagens_sistema = {
    "sem_permissao": "❌ Sem permissão.",
    "apenas_comprador": "❌ Apenas quem abriu o carrinho pode mudar isso.",
    "bot_travado": "❌ **Contas sendo upadas**, aguarde a finalização!",
    "sem_estoque": "❌ Produto sem estoque no momento.",
    "compra_aprovada": "🎉 **COMPRA APROVADA!!** Seu produto foi enviado no seu PV/DM! Obrigado pela preferência!\n\n⏳ *O carrinho fechará automaticamente em 5 minutos.*",
    "carrinho_cancelado": "❌ Cancelando e fechando...",
    "pix_enviado": "✅ PIX enviado!",
    "compra_ja_realizada": "🎉 **COMPRA REALIZADA COM SUCESSO!** Fechando carrinho...",
    "alerta_pix_carrinho": "⚠️ **AVISO:** Seu pedido está pronto.\n\n📊 **RESUMO INTELIGENTE:**\n📦 **Produto:** {produto_nome}\n📦 **Quantidade:** {qtd}x\n💰 **Valor Total:** R$ `{total}`\n\n🔑 **Chave PIX:** `{chave}`\n\n*entrega automática.*",
    "dm_produto_entregue": "🎁 **Sua compra do produto '{produto_nome}' foi aprovada!**\n📦 Aqui está seu produto:\n`{produto}`",
    "dm_fechada_aviso": "⚠️ {cliente}, sua DM está fechada! Abra para receber o produto enviado pelo suporte.",
    "msg_feedback_ping": "⚠️ {cliente}, por favor deixe seu feedback sobre a compra!",
    "msg_quantidade_invalida": "❌ Digite um número válido maior que 0!",
    "msg_estoque_insuficiente": "❌ Estoque insuficiente! Temos apenas `{estoque}` disponíveis neste painel.",
    "msg_fora_de_carrinho": "❌ Este comando só pode ser usado dentro de um canal de carrinho ativo!",
    "aviso_alerta_pv": "⚠️ EI ACORDA! Tem carrinho aberto aguardando atendimento: {canal_nome}!\nEnvie uma mensagem no canal do carrinho para parar este alerta.",
    "msg_gerando_pix": "⏳ *Aguarde uns instantes gerando PIX...*",
    "carrinho_aberto_sucesso": "✅ Carrinho aberto: {canal}",
    "embed_carrinho_titulo": "🛒 Painel do Carrinho",
    "embed_carrinho_desc": "Produto selecionado: **{produto_nome}**\n\n📦 **Quantidade atual:** `{qtd}x`",
    "embed_aprovada_titulo": "🎉 COMPRA REALIZADA COM SUCESSO!",
    "btn_abrir_carrinho": "🛒 Comprar",
    "btn_confirmar_compra": "COMPRA",
    "btn_mudar_qtd": "🔢 QUANTIDADE",
    "btn_cancelar_compra": "CANCELA"
}

chave_pix_global = "Não configurada"

def tem_permissao(interaction: discord.Interaction):
    return interaction.user.id in donos_permitidos

def formatar_texto(template: str, **kwargs):
    try:
        return template.format(**kwargs)
    except Exception:
        return template

async def enviar_log(guild, mensagem_embed):
    global canal_logs_id
    if canal_logs_id:
        canal = guild.get_channel(canal_logs_id)
        if not canal:
            try: canal = await guild.fetch_channel(canal_logs_id)
            except: canal = None
        if canal:
            await canal.send(embed=mensagem_embed)

async def atualizar_embed_painel_especifico(guild, msg_id):
    if msg_id in paineis_produtos:
        p_info = paineis_produtos[msg_id]
        try:
            canal = guild.get_channel(p_info["canal_id"])
            if canal:
                msg = await canal.fetch_message(msg_id)
                embed = discord.Embed(title=p_info["titulo"], description=p_info["descricao"], color=discord.Color.blue())
                embed.add_field(name="📦 Estoque", value=f"`{p_info['estoque']}` disponíveis", inline=True)
                embed.add_field(name="💵 Valor Unitário", value=f"R$ `{p_info['preco']:.2f}`", inline=True)
                if p_info["foto"]:
                    embed.set_image(url=p_info["foto"])
                await msg.edit(embed=embed, view=BotaoAbrirCarrinho())
        except Exception as e:
            print(f"Erro ao atualizar painel {msg_id}: {e}")

@bot.event
async def on_ready():
    print(f"🟢 {bot.user.name} online. Operando de forma bruta e direta.")

@bot.event
async def on_message(message):
    global msg_anuncio_anterior
    if message.author.id == bot.user.id: return

    if message.guild and message.author.id in donos_permitidos:
        if message.channel.id in carrinhos_ativos_alerta:
            carrinhos_ativos_alerta.discard(message.channel.id)

    if canal_anuncio_id and message.channel.id == canal_anuncio_id and texto_anuncio_auto:
        if msg_anuncio_anterior:
            try: await msg_anuncio_anterior.delete()
            except: pass
        embed_anuncio = discord.Embed(description=texto_anuncio_auto, color=discord.Color.gold(), timestamp=datetime.now())
        msg_anuncio_anterior = await message.channel.send(embed=embed_anuncio, view=ViewMensagemAutomatica())

async def alertar_dono_no_pv(canal_id, canal_nome):
    dono_id = donos_permitidos[0]
    try:
        dono = await bot.fetch_user(dono_id)
        while canal_id in carrinhos_ativos_alerta:
            texto_pv = formatar_texto(mensagens_sistema["aviso_alerta_pv"], canal_nome=canal_nome)
            await dono.send(texto_pv)
            await asyncio.sleep(5)
    except Exception as e:
        pass

# ================= COMANDO: EDIÇÃO DE PAINEL DIRETA (SEM MODAL, COM EMOJIS NATIVOS) =================

@bot.tree.command(name="editar_painel", description="Edita o painel direto pelo comando (suporta emojis nativos do Discord).")
@app_commands.describe(
    msg_id="ID da mensagem do painel que quer editar", 
    campo="Qual parte do painel você vai mudar?", 
    novo_valor="O novo texto/valor (jogue os emojis aqui)"
)
@app_commands.choices(campo=[
    app_commands.Choice(name="Título", value="titulo"),
    app_commands.Choice(name="Descrição", value="descricao"),
    app_commands.Choice(name="Estoque", value="estoque"),
    app_commands.Choice(name="Preço", value="preco"),
    app_commands.Choice(name="Foto", value="foto")
])
async def editar_painel(interaction: discord.Interaction, msg_id: str, campo: app_commands.Choice[str], novo_valor: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    try:
        msg_id_int = int(msg_id)
    except ValueError:
        await interaction.response.send_message("❌ O ID da mensagem precisa ser um número.", ephemeral=True)
        return

    if msg_id_int not in paineis_produtos:
        await interaction.response.send_message("❌ Painel não encontrado na memória.", ephemeral=True)
        return
        
    p_info = paineis_produtos[msg_id_int]
    chave = campo.value
    
    if chave == "estoque":
        try: 
            p_info["estoque"] = int(novo_valor)
        except ValueError: 
            await interaction.response.send_message("❌ Estoque precisa ser um número inteiro.", ephemeral=True)
            return
    elif chave == "preco":
        try: 
            p_info["preco"] = float(novo_valor.replace(",", "."))
        except ValueError: 
            await interaction.response.send_message("❌ Preço precisa ser número.", ephemeral=True)
            return
    elif chave == "foto":
        p_info["foto"] = novo_valor if novo_valor.lower() != "nenhuma" else None
    else:
        p_info[chave] = novo_valor
        
    await atualizar_embed_painel_especifico(interaction.guild, msg_id_int)
    await interaction.response.send_message(f"✅ Alteração efetuada com sucesso no campo `{campo.name}`!", ephemeral=True)

# ================= COMANDO: COMPRA FAKE =================

@bot.tree.command(name="compra_fake", description="Gera um anúncio de compra aprovada FAKE.")
async def compra_fake(interaction: discord.Interaction, usuario: discord.User, produto: str, quantidade: int, valor_pago: float):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    if not canal_aprovadas_id:
        await interaction.response.send_message("❌ Canal de aprovadas não configurado. Use /set_canal_aprovadas.", ephemeral=True)
        return

    c_aprovadas = interaction.guild.get_channel(canal_aprovadas_id)
    avatar_url = usuario.display_avatar.url if usuario.avatar else bot.user.display_avatar.url

    embed_grande = discord.Embed(
        title=mensagens_sistema["embed_aprovada_titulo"],
        description=(
            f"Agradecemos pela preferência, {usuario.mention}!\n\n"
            f"🛒 **Resumo da Compra:**\n"
            f"📦 **Produto:** `{produto}`\n"
            f"🔢 **Quantidade:** `{quantidade}x`\n"
            f"💸 **Valor Pago:** R$ `{valor_pago:.2f}`"
        ),
        color=discord.Color.brand_green(),
        timestamp=datetime.now()
    )
    embed_grande.set_author(name=f"Cliente: {usuario.name}", icon_url=avatar_url)
    embed_grande.set_thumbnail(url=avatar_url)
    
    await c_aprovadas.send(embed=embed_grande)
    await interaction.response.send_message("✅ Embed de compra fake despachado.", ephemeral=True)

# ================= COMANDO DE RENDIMENTO =================

@bot.tree.command(name="rendimento", description="Exibe o painel financeiro.")
async def rendimento(interaction: discord.Interaction):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    agora = datetime.now()
    total_faturamento = sum(v["valor"] for v in historico_vendas)
    total_vendas = len(historico_vendas)
    total_itens = sum(v["qtd"] for v in historico_vendas)
    faturamento_hoje = sum(v["valor"] for v in historico_vendas if v["data"].date() == agora.date())
    faturamento_mes = sum(v["valor"] for v in historico_vendas if v["data"].month == agora.month and v["data"].year == agora.year)

    produtos_contagem = {}
    for v in historico_vendas:
        prod = v["produto"]
        produtos_contagem[prod] = produtos_contagem.get(prod, 0) + v["qtd"]
    produto_mais_vendido = max(produtos_contagem, key=produtos_contagem.get) if produtos_contagem else "Nenhum"

    embed = discord.Embed(title="📊 PAINEL DE RENDIMENTO FINANCEIRO", color=discord.Color.gold(), timestamp=agora)
    embed.add_field(name="💰 Faturamento Total", value=f"R$ `{total_faturamento:.2f}`", inline=True)
    embed.add_field(name="📅 Faturamento Hoje", value=f"R$ `{faturamento_hoje:.2f}`", inline=True)
    embed.add_field(name="🗓️ Faturamento Mês", value=f"R$ `{faturamento_mes:.2f}`", inline=True)
    embed.add_field(name="📦 Vendas Aprovadas", value=f"`{total_vendas}` vendas", inline=True)
    embed.add_field(name="🔢 Itens Entregues", value=f"`{total_itens}` unidades", inline=True)
    embed.add_field(name="🏆 Produto Mais Vendido", value=f"`{produto_mais_vendido}`", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= COMANDOS DE GERENCIAMENTO =================

@bot.tree.command(name="enviar_pv", description="Manda uma mensagem direta no PV do usuário.")
async def enviar_pv(interaction: discord.Interaction, usuario: discord.User, mensagem: str):
    if not tem_permissao(interaction): return
    try:
        await usuario.send(mensagem)
        await interaction.response.send_message(f"✅ PV enviado para {usuario.mention}!", ephemeral=True)
    except:
        await interaction.response.send_message(f"❌ DM do {usuario.mention} tá fechada.", ephemeral=True)

@bot.tree.command(name="add_dono", description="Adiciona permissão total a um usuário.")
async def add_dono(interaction: discord.Interaction, usuario: discord.User):
    if not tem_permissao(interaction): return
    if usuario.id not in donos_permitidos:
        donos_permitidos.append(usuario.id)
        await interaction.response.send_message(f"✅ {usuario.mention} agora tem admin do bot.", ephemeral=True)

@bot.tree.command(name="criar_painel", description="Cria um painel de vendas no chat.")
async def criar_painel(interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, descricao: str, estoque: int, preco: float, foto: str = None):
    if not tem_permissao(interaction): return

    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.blue())
    embed.add_field(name="📦 Estoque", value=f"`{estoque}` disponíveis", inline=True)
    embed.add_field(name="💵 Valor Unitário", value=f"R$ `{preco:.2f}`", inline=True)
    if foto and foto.startswith("http"): embed.set_image(url=foto)

    msg = await canal.send(embed=embed, view=BotaoAbrirCarrinho())
    paineis_produtos[msg.id] = {"titulo": titulo, "descricao": descricao, "estoque": estoque, "preco": preco, "foto": foto, "canal_id": canal.id}
    await interaction.response.send_message(f"✅ Painel criado. Pra mudar, usa /editar_painel {msg.id}", ephemeral=True)

@bot.tree.command(name="config_pix", description="Configura a chave PIX geral do sistema.")
async def config_pix(interaction: discord.Interaction, chave: str):
    global chave_pix_global
    if not tem_permissao(interaction): return
    chave_pix_global = chave
    await interaction.response.send_message(f"✅ Chave PIX: `{chave}`", ephemeral=True)

@bot.tree.command(name="logs", description="Define o canal onde os logs vão cair.")
async def config_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_logs_id
    if not tem_permissao(interaction): return
    canal_logs_id = canal.id
    await interaction.response.send_message(f"📢 Logs vão pro canal {canal.mention}.", ephemeral=True)

@bot.tree.command(name="set_canal_aprovadas", description="Define onde as compras aprovadas aparecem publicamente.")
async def set_canal_aprovadas(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_aprovadas_id
    if not tem_permissao(interaction): return
    canal_aprovadas_id = canal.id
    await interaction.response.send_message(f"🎉 Aprovadas vão pro canal {canal.mention}", ephemeral=True)

@bot.tree.command(name="mandar_pix", description="Despacha os dados do PIX no carrinho.")
async def mandar_pix(interaction: discord.Interaction, chave: str = None):
    if not tem_permissao(interaction): return
    canal_id = interaction.channel.id
    if canal_id not in dados_carrinhos:
        return await interaction.response.send_message(mensagens_sistema["msg_fora_de_carrinho"], ephemeral=True)
        
    carrinhos_aguardando_pix[canal_id] = True
    chave_usar = chave if chave else chave_pix_global
    info_carrinho = dados_carrinhos[canal_id]
    total_pagar = info_carrinho["preco"] * info_carrinho["qtd"]
    
    await interaction.response.send_message(mensagens_sistema["pix_enviado"], ephemeral=True)
    texto_resumo_pix = formatar_texto(mensagens_sistema["alerta_pix_carrinho"], produto_nome=info_carrinho["produto_nome"], qtd=info_carrinho["qtd"], total=f"{total_pagar:.2f}", chave=chave_usar)
    await interaction.channel.send(texto_resumo_pix)

@bot.tree.command(name="aprovar", description="Aprova a compra do carrinho e desconta do estoque.")
async def aprovar(interaction: discord.Interaction, produto: str):
    if not tem_permissao(interaction): return
    canal_id = interaction.channel.id
    if canal_id not in dados_carrinhos:
        return await interaction.response.send_message(mensagens_sistema["msg_fora_de_carrinho"], ephemeral=True)

    info_carrinho = dados_carrinhos[canal_id]
    cliente_id = info_carrinho["cliente_id"]
    qtd = info_carrinho["qtd"]
    panel_id = info_carrinho["panel_id"]
    nome_produto = info_carrinho["produto_nome"]
    total_venda = info_carrinho["preco"] * qtd

    historico_vendas.append({"valor": total_venda, "qtd": qtd, "produto": nome_produto, "data": datetime.now()})
    cliente = await bot.fetch_user(cliente_id)

    if panel_id in paineis_produtos:
        paineis_produtos[panel_id]["estoque"] = max(0, paineis_produtos[panel_id]["estoque"] - qtd)
        await atualizar_embed_painel_especifico(interaction.guild, panel_id)

    carrinhos_aprovados.add(canal_id)
    await interaction.response.send_message(f"✅ Venda validada. R$ `{total_venda:.2f}` pro caixa.", ephemeral=True)
    await interaction.channel.send(mensagens_sistema["compra_aprovada"])

    try:
        await cliente.send(formatar_texto(mensagens_sistema["dm_produto_entregue"], produto_nome=nome_produto, produto=produto))
    except:
        await interaction.channel.send(formatar_texto(mensagens_sistema["dm_fechada_aviso"], cliente=cliente.mention))

    if canal_aprovadas_id:
        c_aprovadas = interaction.guild.get_channel(canal_aprovadas_id)
        if c_aprovadas:
            avatar = cliente.display_avatar.url if cliente.avatar else bot.user.display_avatar.url
            embed_apv = discord.Embed(
                title=mensagens_sistema["embed_aprovada_titulo"],
                description=f"Agradecemos pela preferência, {cliente.mention}!\n\n🛒 **Resumo da Compra:**\n📦 **Produto:** `{nome_produto}`\n🔢 **Quantidade:** `{qtd}x`\n💸 **Valor Pago:** R$ `{total_venda:.2f}`",
                color=discord.Color.brand_green(),
                timestamp=datetime.now()
            )
            embed_apv.set_author(name=cliente.name, icon_url=avatar)
            embed_apv.set_thumbnail(url=avatar)
            await c_aprovadas.send(embed=embed_apv)
            
            async def ping_feedback():
                msg = await c_aprovadas.send(formatar_texto(mensagens_sistema["msg_feedback_ping"], cliente=cliente.mention))
                await asyncio.sleep(10)
                try: await msg.delete()
                except: pass
            asyncio.create_task(ping_feedback())

    embed_log = discord.Embed(title="💰 VENDA FINALIZADA", color=discord.Color.green(), timestamp=datetime.now())
    embed_log.add_field(name="Cliente", value=cliente.mention)
    embed_log.add_field(name="Produto", value=f"`{nome_produto}`")
    embed_log.add_field(name="Total", value=f"R$ `{total_venda:.2f}`")
    await enviar_log(interaction.guild, embed_log)

    async def fechar_carrinho():
        await asyncio.sleep(300)
        try:
            carrinhos_ativos_alerta.discard(canal_id)
            dados_carrinhos.pop(canal_id, None)
            await interaction.channel.delete()
        except: pass
    asyncio.create_task(fechar_carrinho())

# ================= CLASSES DE BOTÕES E INTERFACES =================

class ViewMensagemAutomatica(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_auto_disable")
    async def btn_auto(self, i: discord.Interaction, b: discord.ui.Button): pass

class BotaoAbrirCarrinho(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.btn_compra.label = mensagens_sistema["btn_abrir_carrinho"]

    @discord.ui.button(label="🛒 Comprar", style=discord.ButtonStyle.green, custom_id="btn_abrir")
    async def btn_compra(self, interaction: discord.Interaction, button: discord.ui.Button):
        if status_sistema == "upando":
            return await interaction.response.send_message(mensagens_sistema["bot_travado"], ephemeral=True)

        panel_id = interaction.message.id
        painel_info = paineis_produtos.get(panel_id)

        if painel_info and painel_info["estoque"] <= 0:
            return await interaction.response.send_message(mensagens_sistema["sem_estoque"], ephemeral=True)

        guild = interaction.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        for d in donos_permitidos:
            dm = guild.get_member(d)
            if dm: overwrites[dm] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        cc = await guild.create_text_channel(name=f"🛒-carrinho-{interaction.user.name}", category=interaction.channel.category, overwrites=overwrites)
        await interaction.response.send_message(formatar_texto(mensagens_sistema["carrinho_aberto_sucesso"], canal=cc.mention), ephemeral=True)

        nome = painel_info["titulo"] if painel_info else "Produto"
        preco = painel_info["preco"] if painel_info else 0.0

        dados_carrinhos[cc.id] = {"cliente_id": interaction.user.id, "qtd": 1, "panel_id": panel_id, "produto_nome": nome, "preco": preco}

        await cc.send("@everyone")
        emb = discord.Embed(title=mensagens_sistema["embed_carrinho_titulo"], description=formatar_texto(mensagens_sistema["embed_carrinho_desc"], produto_nome=nome, qtd=1), color=discord.Color.light_grey())
        await cc.send(embed=emb, view=InterfaceCarrinho(interaction.user.id))

        elog = discord.Embed(title="🛒 CARRINHO ABERTO", color=discord.Color.blue(), timestamp=datetime.now())
        elog.add_field(name="Cliente", value=interaction.user.mention); elog.add_field(name="Produto", value=f"`{nome}`")
        await enviar_log(guild, elog)

        carrinhos_ativos_alerta.add(cc.id)
        asyncio.create_task(alertar_dono_no_pv(cc.id, cc.name))

class ModalQuantidade(discord.ui.Modal, title="Digite a quantidade"):
    qtd_in = discord.ui.TextInput(label="Itens", placeholder="Num", min_length=1, max_length=3)
    def __init__(self, c_id):
        super().__init__()
        self.c_id = c_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.qtd_in.value)
            if qtd <= 0: raise ValueError
        except: return await interaction.response.send_message(mensagens_sistema["msg_quantidade_invalida"], ephemeral=True)

        cid = interaction.channel.id
        info = dados_carrinhos.get(cid, {})
        pid = info.get("panel_id")

        if pid in paineis_produtos:
            est = paineis_produtos[pid]["estoque"]
            if qtd > est: return await interaction.response.send_message(formatar_texto(mensagens_sistema["msg_estoque_insuficiente"], estoque=est), ephemeral=True)

        dados_carrinhos[cid]["qtd"] = qtd
        tot = info.get("preco", 0.0) * qtd
        desc = formatar_texto(mensagens_sistema["embed_carrinho_desc"], produto_nome=info.get("produto_nome", "Produto"), qtd=qtd) + f"\n💰 **Subtotal:** R$ `{tot:.2f}`"
        
        await interaction.response.edit_message(embed=discord.Embed(title=mensagens_sistema["embed_carrinho_titulo"], description=desc, color=discord.Color.green()), view=InterfaceCarrinho(self.c_id))

class InterfaceCarrinho(discord.ui.View):
    def __init__(self, c_id):
        super().__init__(timeout=None)
        self.c_id = c_id
        self.btn_conf.label = mensagens_sistema["btn_confirmar_compra"]
        self.btn_qtd.label = mensagens_sistema["btn_mudar_qtd"]
        self.btn_canc.label = mensagens_sistema["btn_cancelar_compra"]

    @discord.ui.button(label="COMPRA", style=discord.ButtonStyle.green, custom_id="c_conf")
    async def btn_conf(self, interaction: discord.Interaction, button: discord.ui.Button):
        carrinhos_aguardando_pix[interaction.channel.id] = False
        carrinhos_ativos_alerta.discard(interaction.channel.id)
        await interaction.response.send_message(mensagens_sistema["msg_gerando_pix"])

    @discord.ui.button(label="QUANTIDADE", style=discord.ButtonStyle.primary, custom_id="c_qtd")
    async def btn_qtd(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.c_id: return await interaction.response.send_message(mensagens_sistema["apenas_comprador"], ephemeral=True)
        await interaction.response.send_modal(ModalQuantidade(self.c_id))

    @discord.ui.button(label="CANCELA", style=discord.ButtonStyle.danger, custom_id="c_canc")
    async def btn_canc(self, interaction: discord.Interaction, button: discord.ui.Button):
        cid = interaction.channel.id
        carrinhos_ativos_alerta.discard(cid)
        if cid in carrinhos_aprovados:
            await interaction.response.send_message(mensagens_sistema["compra_ja_realizada"])
            await asyncio.sleep(2)
            try: await interaction.channel.delete()
            except: pass
            return

        elog = discord.Embed(title="❌ CANCELADO", color=discord.Color.red(), timestamp=datetime.now())
        elog.add_field(name="User", value=interaction.user.mention)
        await enviar_log(interaction.guild, elog)
        await interaction.response.send_message(mensagens_sistema["carrinho_cancelado"])
        await asyncio.sleep(2)
        try: await interaction.channel.delete()
        except: pass

if __name__ == "__main__":
    manter_online()
    bot.run(TOKEN_BOT)

