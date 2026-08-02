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

# Estruturas para múltiplos painéis e carrinhos
paineis_produtos = {}  # msg_id -> {titulo, descricao, preco, estoque, foto, canal_id}
carrinhos_aguardando_pix = {}
dados_carrinhos = {}   # canal_id -> {cliente_id, qtd, panel_id, produto_nome, preco}
carrinhos_aprovados = set()
carrinhos_ativos_alerta = set()

# HISTÓRICO FINANCEIRO
historico_vendas = []  # List de dicts: {"valor": float, "qtd": int, "produto": str, "data": datetime}

# Controle de Anúncio Automático
canal_anuncio_id = None
texto_anuncio_auto = None
msg_anuncio_anterior = None

# DICIONÁRIO DE TEXTOS DO SISTEMA
mensagens_sistema = {
    "sem_permissao": "❌ Sem permissão.",
    "apenas_comprador": "❌ Apenas quem abriu o carrinho pode mudar isso.",
    "bot_travado": "❌ **Contas sendo upadas**, aguarde a finalização!",
    "sem_estoque": "❌ Produto sem estoque no momento.",
    "compra_aprovada": "🎉 **COMPRA APROVADA!!** Seu produto foi enviado no seu PV/DM! Obrigado pela preferência! ✨\n\n⏳ *O carrinho fechará automaticamente em 5 minutos.*",
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

    # Embeds
    "embed_carrinho_titulo": "🛒 Painel do Carrinho",
    "embed_carrinho_desc": "Produto selecionado: **{produto_nome}**\n\n📦 **Quantidade atual:** `{qtd}x`",
    "embed_aprovada_titulo": "🎉 COMPRA REALIZADA COM SUCESSO!",

    # Botões
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
    print(f"🟢 {bot.user.name} online com sistema de rendimentos ativo!")

@bot.event
async def on_message(message):
    global msg_anuncio_anterior

    if message.author.id == bot.user.id:
        return

    if message.guild and message.author.id in donos_permitidos:
        if message.channel.id in carrinhos_ativos_alerta:
            carrinhos_ativos_alerta.discard(message.channel.id)

    if canal_anuncio_id and message.channel.id == canal_anuncio_id and texto_anuncio_auto:
        if msg_anuncio_anterior:
            try: await msg_anuncio_anterior.delete()
            except: pass

        embed_anuncio = discord.Embed(
            description=texto_anuncio_auto,
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
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
        print(f"Erro ao enviar mensagem no PV: {e}")

# ================= VIEWS E BOTÕES =================

class ViewMensagemAutomatica(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_msg_auto_disabled")
    async def btn_auto(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

# ================= COMANDO DE RENDIMENTO FINANCEIRO =================

@bot.tree.command(name="rendimento", description="Exibe o painel financeiro e métricas de vendas reais em tempo real.")
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

    # Cálculo do produto mais vendido
    produtos_contagem = {}
    for v in historico_vendas:
        prod = v["produto"]
        produtos_contagem[prod] = produtos_contagem.get(prod, 0) + v["qtd"]

    produto_mais_vendido = max(produtos_contagem, key=produtos_contagem.get) if produtos_contagem else "Nenhum"

    embed = discord.Embed(
        title="📊 PAINEL DE RENDIMENTO FINANCEIRO",
        description="Métricas calculadas em tempo real com base nas vendas aprovadas.",
        color=discord.Color.gold(),
        timestamp=agora
    )
    embed.add_field(name="💰 Faturamento Total", value=f"R$ `{total_faturamento:.2f}`", inline=True)
    embed.add_field(name="📅 Faturamento Hoje", value=f"R$ `{faturamento_hoje:.2f}`", inline=True)
    embed.add_field(name="🗓️ Faturamento Mês", value=f"R$ `{faturamento_mes:.2f}`", inline=True)
    embed.add_field(name="📦 Vendas Aprovadas", value=f"`{total_vendas}` vendas", inline=True)
    embed.add_field(name="🔢 Itens Entregues", value=f"`{total_itens}` unidades", inline=True)
    embed.add_field(name="🏆 Produto Mais Vendido", value=f"`{produto_mais_vendido}`", inline=False)
    embed.set_footer(text="Sistema de Controle Financeiro Automático")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= DEMAIS COMANDOS =================

@bot.tree.command(name="enviar_pv", description="Envia uma mensagem direta no PV de um usuário específico.")
async def enviar_pv(interaction: discord.Interaction, usuario: discord.User, mensagem: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    try:
        await usuario.send(mensagem)
        await interaction.response.send_message(f"✅ Mensagem enviada no PV de {usuario.mention}!", ephemeral=True)
    except Exception:
        await interaction.response.send_message(f"❌ DM fechada para {usuario.mention}.", ephemeral=True)

@bot.tree.command(name="criar_painel", description="Cria um novo painel de vendas independente sem mexer nos existentes.")
async def criar_painel(interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, descricao: str, estoque: int, preco: float, foto: str = None):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.blue())
    embed.add_field(name="📦 Estoque", value=f"`{estoque}` disponíveis", inline=True)
    embed.add_field(name="💵 Valor Unitário", value=f"R$ `{preco:.2f}`", inline=True)

    if foto and (foto.startswith("http://") or foto.startswith("https://")):
        embed.set_image(url=foto)
    else:
        foto = None

    msg = await canal.send(embed=embed, view=BotaoAbrirCarrinho())

    paineis_produtos[msg.id] = {
        "titulo": titulo,
        "descricao": descricao,
        "estoque": estoque,
        "preco": preco,
        "foto": foto,
        "canal_id": canal.id
    }

    await interaction.response.send_message(f"✅ Painel **'{titulo}'** criado com sucesso em {canal.mention}!", ephemeral=True)

@bot.tree.command(name="add_dono", description="Adiciona permissão a um usuário.")
async def add_dono(interaction: discord.Interaction, usuario: discord.User):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    if usuario.id not in donos_permitidos:
        donos_permitidos.append(usuario.id)
        await interaction.response.send_message(f"✅ {usuario.mention} agora possui permissão!", ephemeral=True)

@bot.tree.command(name="config_pix", description="Configura a chave PIX padrão.")
async def config_pix(interaction: discord.Interaction, chave: str):
    global chave_pix_global
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    chave_pix_global = chave
    await interaction.response.send_message(f"✅ Chave PIX padrão definida: `{chave}`", ephemeral=True)

@bot.tree.command(name="logs", description="Define o canal de logs.")
async def config_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_logs_id
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    canal_logs_id = canal.id
    await interaction.response.send_message(f"📢 Canal de logs definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="set_canal_aprovadas", description="Define o canal público para os painéis de compra aprovada.")
async def set_canal_aprovadas(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_aprovadas_id
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    canal_aprovadas_id = canal.id
    await interaction.response.send_message(f"🎉 Canal de anúncios públicos definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="mandar_pix", description="Envia o PIX calculado baseado na quantidade do carrinho.")
async def mandar_pix(interaction: discord.Interaction, chave: str = None):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    canal_id = interaction.channel.id
    carrinhos_aguardando_pix[canal_id] = True

    chave_usar = chave if chave else chave_pix_global
    info_carrinho = dados_carrinhos.get(canal_id, {"qtd": 1, "preco": 0.0, "produto_nome": "Produto"})
    qtd = info_carrinho["qtd"]
    preco_un = info_carrinho.get("preco", 0.0)
    total_pagar = preco_un * qtd

    await interaction.response.send_message(mensagens_sistema["pix_enviado"], ephemeral=True)

    texto_resumo_pix = formatar_texto(
        mensagens_sistema["alerta_pix_carrinho"],
        produto_nome=info_carrinho.get("produto_nome", "Produto"),
        qtd=qtd,
        total=f"{total_pagar:.2f}",
        chave=chave_usar
    )
    await interaction.channel.send(texto_resumo_pix)

@bot.tree.command(name="aprovar", description="Aprova a compra, salva o faturamento, baixa estoque e anuncia.")
async def aprovar(interaction: discord.Interaction, produto: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    canal_id = interaction.channel.id

    if canal_id not in dados_carrinhos:
        await interaction.response.send_message(mensagens_sistema["msg_fora_de_carrinho"], ephemeral=True)
        return

    info_carrinho = dados_carrinhos[canal_id]
    cliente_id = info_carrinho["cliente_id"]
    qtd_comprada = info_carrinho["qtd"]
    panel_id = info_carrinho.get("panel_id")
    nome_produto = info_carrinho.get("produto_nome", "Produto")
    preco_un = info_carrinho.get("preco", 0.0)

    total_venda = preco_un * qtd_comprada

    # REGISTRO NO HISTÓRICO DE RENDIMENTOS
    historico_vendas.append({
        "valor": total_venda,
        "qtd": qtd_comprada,
        "produto": nome_produto,
        "data": datetime.now()
    })

    cliente = await bot.fetch_user(cliente_id)

    # Baixa estoque do painel específico
    if panel_id in paineis_produtos:
        if paineis_produtos[panel_id]["estoque"] >= qtd_comprada:
            paineis_produtos[panel_id]["estoque"] -= qtd_comprada
        else:
            paineis_produtos[panel_id]["estoque"] = 0
        await atualizar_embed_painel_especifico(interaction.guild, panel_id)

    carrinhos_aprovados.add(canal_id)

    await interaction.response.send_message(f"✅ Venda aprovada! R$ `{total_venda:.2f}` adicionados ao rendimento.", ephemeral=True)
    await interaction.channel.send(mensagens_sistema["compra_aprovada"])

    # Entrega privada via DM
    try:
        texto_dm = formatar_texto(mensagens_sistema["dm_produto_entregue"], produto_nome=nome_produto, produto=produto)
        await cliente.send(texto_dm)
    except:
        try:
            texto_dm_fechada = formatar_texto(mensagens_sistema["dm_fechada_aviso"], cliente=cliente.mention)
            await interaction.channel.send(texto_dm_fechada)
        except: pass

    # Embed de Anúncio Público Grande
    if canal_aprovadas_id:
        c_aprovadas = interaction.guild.get_channel(canal_aprovadas_id)
        if c_aprovadas:
            embed_grande = discord.Embed(
                title="🎉 COMPRA APROVADA - OBRIGADO PELA PREFERÊNCIA!",
                description=(
                    f"👤 **Cliente:** {cliente.mention}\n\n"
                    f"📦 **Produto:** `{nome_produto}`\n\n"
                    f"🔢 **Quantidade:** `{qtd_comprada}x`\n\n"
                    f"✨ *O produto foi entregue automaticamente com segurança via Mensagem Direta (DM)!*"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed_grande.set_thumbnail(url=cliente.display_avatar.url if cliente.avatar else bot.user.display_avatar.url)
            embed_grande.set_footer(text="Agradecemos a sua compra! Volte sempre.")

            await c_aprovadas.send(embed=embed_grande)

            async def marcar_e_apagar_feedback():
                texto_ping = formatar_texto(mensagens_sistema["msg_feedback_ping"], cliente=cliente.mention)
                msg_ping = await c_aprovadas.send(texto_ping)
                await asyncio.sleep(10)
                try: await msg_ping.delete()
                except: pass

            asyncio.create_task(marcar_e_apagar_feedback())

    embed_log = discord.Embed(title="💰 VENDA REALIZADA", color=discord.Color.green(), timestamp=datetime.now())
    embed_log.add_field(name="Cliente", value=cliente.mention)
    embed_log.add_field(name="Produto", value=f"`{nome_produto}`")
    embed_log.add_field(name="Quantidade", value=f"`{qtd_comprada}`")
    embed_log.add_field(name="Total Recebido", value=f"R$ `{total_venda:.2f}`")
    await enviar_log(interaction.guild, embed_log)

    async def fechar_carrinho_breve():
        await asyncio.sleep(300)
        try:
            carrinhos_ativos_alerta.discard(canal_id)
            carrinhos_aprovados.discard(canal_id)
            dados_carrinhos.pop(canal_id, None)
            await interaction.channel.delete()
        except: pass
    asyncio.create_task(fechar_carrinho_breve())

# ================= INTERFACES E BOTÕES =================

class BotaoAbrirCarrinho(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.btn_compra.label = mensagens_sistema["btn_abrir_carrinho"]

    @discord.ui.button(label="🛒 Comprar", style=discord.ButtonStyle.green, custom_id="abrir_carrinho_btn")
    async def btn_compra(self, interaction: discord.Interaction, button: discord.ui.Button):
        if status_sistema == "upando":
            await interaction.response.send_message(mensagens_sistema["bot_travado"], ephemeral=True)
            return

        panel_id = interaction.message.id
        painel_info = paineis_produtos.get(panel_id)

        if painel_info and painel_info["estoque"] <= 0:
            await interaction.response.send_message(mensagens_sistema["sem_estoque"], ephemeral=True)
            return

        guild = interaction.guild

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for dono_id in donos_permitidos:
            dono_member = guild.get_member(dono_id)
            if dono_member:
                overwrites[dono_member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        canal_carrinho = await guild.create_text_channel(
            name=f"🛒-carrinho-{interaction.user.name}",
            category=interaction.channel.category,
            overwrites=overwrites
        )

        msg_sucesso = formatar_texto(mensagens_sistema["carrinho_aberto_sucesso"], canal=canal_carrinho.mention)
        await interaction.response.send_message(msg_sucesso, ephemeral=True)

        nome_prod = painel_info["titulo"] if painel_info else "Produto"
        preco_prod = painel_info["preco"] if painel_info else 0.0

        dados_carrinhos[canal_carrinho.id] = {
            "cliente_id": interaction.user.id,
            "qtd": 1,
            "panel_id": panel_id,
            "produto_nome": nome_prod,
            "preco": preco_prod
        }

        await canal_carrinho.send("@everyone")

        desc_embed = formatar_texto(mensagens_sistema["embed_carrinho_desc"], produto_nome=nome_prod, qtd=1)
        embed_carrinho = discord.Embed(
            title=mensagens_sistema["embed_carrinho_titulo"],
            description=desc_embed,
            color=discord.Color.light_grey()
        )
        await canal_carrinho.send(embed=embed_carrinho, view=InterfaceCarrinho(interaction.user.id))

        embed_log = discord.Embed(title="🛒 CARRINHO ABERTO", color=discord.Color.blue(), timestamp=datetime.now())
        embed_log.add_field(name="Cliente", value=interaction.user.mention)
        embed_log.add_field(name="Produto", value=f"`{nome_prod}`")
        embed_log.add_field(name="Canal", value=canal_carrinho.mention)
        await enviar_log(guild, embed_log)

        carrinhos_ativos_alerta.add(canal_carrinho.id)
        asyncio.create_task(alertar_dono_no_pv(canal_carrinho.id, canal_carrinho.name))

class ModalQuantidade(discord.ui.Modal, title="Escolha a Quantidade"):
    quantidade_input = discord.ui.TextInput(label="Quantos itens você quer?", placeholder="Ex: 5", min_length=1, max_length=3)

    def __init__(self, comprador_id):
        super().__init__()
        self.comprador_id = comprador_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade_input.value)
            if qtd <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message(mensagens_sistema["msg_quantidade_invalida"], ephemeral=True)
            return

        canal_id = interaction.channel.id
        info_carrinho = dados_carrinhos.get(canal_id, {})
        panel_id = info_carrinho.get("panel_id")

        if panel_id in paineis_produtos:
            estoque_disp = paineis_produtos[panel_id]["estoque"]
            if qtd > estoque_disp:
                texto_insuf = formatar_texto(mensagens_sistema["msg_estoque_insuficiente"], estoque=estoque_disp)
                await interaction.response.send_message(texto_insuf, ephemeral=True)
                return

        dados_carrinhos[canal_id]["qtd"] = qtd
        nome_prod = info_carrinho.get("produto_nome", "Produto")
        preco_un = info_carrinho.get("preco", 0.0)
        total = preco_un * qtd

        desc_embed = formatar_texto(mensagens_sistema["embed_carrinho_desc"], produto_nome=nome_prod, qtd=qtd) + f"\n💰 **Subtotal:** R$ `{total:.2f}`"
        embed_atualizado = discord.Embed(
            title=mensagens_sistema["embed_carrinho_titulo"],
            description=desc_embed,
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed_atualizado, view=InterfaceCarrinho(self.comprador_id))

class InterfaceCarrinho(discord.ui.View):
    def __init__(self, comprador_id):
        super().__init__(timeout=None)
        self.comprador_id = comprador_id
        self.confirmar.label = mensagens_sistema["btn_confirmar_compra"]
        self.mudar_qtd.label = mensagens_sistema["btn_mudar_qtd"]
        self.cancela.label = mensagens_sistema["btn_cancelar_compra"]

    @discord.ui.button(label="COMPRA", style=discord.ButtonStyle.green, custom_id="btn_confirmar_compra")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(mensagens_sistema["msg_gerando_pix"])
        canal_id = interaction.channel.id
        carrinhos_aguardando_pix[canal_id] = False
        carrinhos_ativos_alerta.discard(canal_id)

    @discord.ui.button(label="🔢 QUANTIDADE", style=discord.ButtonStyle.primary, custom_id="btn_mudar_quantidade")
    async def mudar_qtd(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.comprador_id:
            await interaction.response.send_message(mensagens_sistema["apenas_comprador"], ephemeral=True)
            return
        await interaction.response.send_modal(ModalQuantidade(self.comprador_id))

    @discord.ui.button(label="CANCELA", style=discord.ButtonStyle.danger, custom_id="btn_cancelar_compra")
    async def cancela(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal_id = interaction.channel.id
        carrinhos_ativos_alerta.discard(canal_id)

        if canal_id in carrinhos_aprovados:
            await interaction.response.send_message(mensagens_sistema["compra_ja_realizada"])
            await asyncio.sleep(2)
            try: await interaction.channel.delete()
            except: pass
            return

        embed_log = discord.Embed(title="❌ CARRINHO CANCELADO", color=discord.Color.red(), timestamp=datetime.now())
        embed_log.add_field(name="Quem cancelou", value=interaction.user.mention)
        embed_log.add_field(name="Canal", value=f"`{interaction.channel.name}`")
        await enviar_log(interaction.guild, embed_log)

        await interaction.response.send_message(mensagens_sistema["carrinho_cancelado"])
        await asyncio.sleep(2)
        try: await interaction.channel.delete()
        except: pass

if __name__ == "__main__":
    manter_online()
    bot.run(TOKEN_BOT)

