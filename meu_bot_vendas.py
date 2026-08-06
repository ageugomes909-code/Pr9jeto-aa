import discord
from discord import app_commands
import asyncio
from datetime import datetime
from flask import Flask
from threading import Thread
import os

# --- SISTEMA DE WEB SERVER PARA MANTER O BOT ONLINE ---

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

donos_permitidos = [985441586898939904]
status_sistema = "normal"
canal_logs_id = None
canal_aprovadas_id = None

paineis_produtos = {}  
carrinhos_aguardando_pix = {}
dados_carrinhos = {}   
carrinhos_aprovados = set()
carrinhos_ativos_alerta = set()
historico_vendas = []  

# Configurações Automáticas
canais_reacao_auto = {}      # canal_id -> emoji
canais_mensagem_fixa = {}    # canal_id -> {"texto": texto, "id_mensagem": int}

# DICIONÁRIO DE TEXTOS DO SISTEMA
mensagens_sistema = {
    "sem_permissao": "❌ Você não possui permissão administrativa.",
    "apenas_comprador": "❌ Apenas quem abriu este carrinho pode alterar a quantidade.",
    "sem_estoque": "❌ Este produto está sem estoque no momento.",
    "compra_aprovada": "🎉 **COMPRA APROVADA COM SUCESSO! OBRIGADO PELA CONFIANÇA!** ✨\n\n🎁 *Seu produto foi enviado com segurança no seu PV/DM!*\n⏳ *Este carrinho fechará automaticamente em 5 minutos.*",
    "carrinho_cancelado": "❌ Cancelando e fechando o carrinho em instantes...",
    "pix_enviado": "✅ Dados do PIX enviados no carrinho!",
    "compra_ja_realizada": "🎉 **COMPRA JÁ APROVADA!** Fechando carrinho...",
    "alerta_pix_carrinho": "⚠️ **AVISO:** Seu pedido está pronto para pagamento.\n\n📊 **RESUMO DO PEDIDO:**\n📦 **Produto:** {produto_nome}\n🔢 **Quantidade:** {qtd}x\n💰 **Valor Total:** R$ `{total}`\n\n🔑 **Chave PIX:** `{chave}`\n\n*Aguardando confirmação do pagamento.*",
    "dm_produto_entregue": "🎁 **Sua compra do produto '{produto_nome}' foi aprovada!**\n\n📦 **Aqui está o seu produto:**\n`{produto}`\n\n✨ *Obrigado pela preferência!*",
    "dm_fechada_aviso": "⚠️ {cliente}, sua DM está fechada! Abra o seu privado para receber o produto.",
    "msg_feedback_ping": "⚠️ {cliente}, por favor deixe seu feedback sobre a compra!",
    "msg_quantidade_invalida": "❌ Digite um número válido maior que 0!",
    "msg_estoque_insuficiente": "❌ Estoque insuficiente! Temos apenas `{estoque}` unidades disponíveis.",
    "msg_fora_de_carrinho": "❌ Este comando só pode ser executado dentro de um carrinho ativo!",
    "aviso_alerta_pv": "⚠️ **EI ACORDA!** Tem carrinho aberto aguardando atendimento: {canal_nome}!\nEnvie uma mensagem no canal para parar este alerta.",
    "msg_gerando_pix": "⏳ **GERANDO PIX E CHAMANDO DONO...**",
    "carrinho_aberto_sucesso": "✅ Carrinho aberto com sucesso: {canal}",
    "embed_carrinho_titulo": "🛒 Painel do Carrinho",
    "embed_carrinho_desc": "📦 **Produto selecionado:** {produto_nome}\n🔢 **Quantidade atual:** `{qtd}x`",
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
            try:
                await canal.send(embed=mensagem_embed)
            except Exception as e:
                print(f"Erro ao enviar log: {e}")

@bot.event
async def on_ready():
    print(f"🟢 {bot.user.name} online e pronto para uso!")

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id: 
        return

    # Auto Reação em canais configurados
    if message.channel.id in canais_reacao_auto:
        emoji = canais_reacao_auto[message.channel.id]
        try:
            await message.add_reaction(emoji)
        except Exception as e:
            print(f"Erro na auto-reação: {e}")

    # Mensagem Fixa Automática (Sticky Message)
    if message.channel.id in canais_mensagem_fixa:
        dados_sticky = canais_mensagem_fixa[message.channel.id]
        
        if dados_sticky["id_mensagem"]:
            try:
                msg_antiga = await message.channel.fetch_message(dados_sticky["id_mensagem"])
                await msg_antiga.delete()
            except: 
                pass
        
        view_automatica = discord.ui.View()
        view_automatica.add_item(discord.ui.Button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True))

        try:
            nova_msg = await message.channel.send(content=dados_sticky["texto"], view=view_automatica)
            canais_mensagem_fixa[message.channel.id]["id_mensagem"] = nova_msg.id
        except Exception as e:
            print(f"Erro ao reenviar mensagem fixa: {e}")

    # Interrupção de Alerta no PV quando Dono responde no carrinho
    if message.guild and message.author.id in donos_permitidos:
        if message.channel.id in carrinhos_ativos_alerta:
            carrinhos_ativos_alerta.discard(message.channel.id)

async def alertar_dono_no_pv(canal_id, canal_nome):
    dono_id = donos_permitidos[0]
    try:
        dono = await bot.fetch_user(dono_id)
        while canal_id in carrinhos_ativos_alerta:
            texto_pv = formatar_texto(mensagens_sistema["aviso_alerta_pv"], canal_nome=canal_nome)
            await dono.send(texto_pv)
            await asyncio.sleep(5)
    except Exception:
        pass

# ================= COMANDOS DE ADMINISTRAÇÃO E CONFIGURAÇÃO =================

@bot.tree.command(name="add_dono", description="Adiciona permissão de dono/administrador a um usuário.")
async def add_dono(interaction: discord.Interaction, usuario: discord.User):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    
    if usuario.id not in donos_permitidos:
        donos_permitidos.append(usuario.id)
        await interaction.response.send_message(f"✅ {usuario.mention} agora possui acesso total e visualização de todos os carrinhos!", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Este usuário já é um dono registrado.", ephemeral=True)

@bot.tree.command(name="enviar_pv", description="Envia uma mensagem direta no PV de um usuário.")
async def enviar_pv(interaction: discord.Interaction, usuario: discord.User, mensagem: str):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    try:
        await usuario.send(mensagem)
        await interaction.response.send_message(f"✅ Mensagem enviada com sucesso no PV de {usuario.mention}!", ephemeral=True)
    except:
        await interaction.response.send_message(f"❌ Não foi possível enviar no PV de {usuario.mention} (DM Fechada).", ephemeral=True)

@bot.tree.command(name="anuncio", description="Envia um Embed de anúncio em um canal escolhido.")
async def anuncio(interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, descricao: str):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.blue(), timestamp=datetime.now())
    await canal.send(embed=embed)
    await interaction.response.send_message(f"✅ Anúncio enviado em {canal.mention}!", ephemeral=True)

@bot.tree.command(name="limpar", description="Apaga mensagens do canal atual.")
async def limpar(interaction: discord.Interaction, quantidade: int):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deletadas = await interaction.channel.purge(limit=quantidade)
    await interaction.followup.send(f"✅ `{len(deletadas)}` mensagens apagadas com sucesso.")

@bot.tree.command(name="config_pix", description="Configura a chave PIX padrão do sistema.")
async def config_pix(interaction: discord.Interaction, chave: str):
    global chave_pix_global
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    chave_pix_global = chave
    await interaction.response.send_message(f"✅ Chave PIX padrão definida para: `{chave}`", ephemeral=True)

@bot.tree.command(name="logs", description="Define o canal onde serão enviados os logs do sistema.")
async def config_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_logs_id
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    canal_logs_id = canal.id
    await interaction.response.send_message(f"📢 Canal de logs configurado para {canal.mention}.", ephemeral=True)

@bot.tree.command(name="set_canal_aprovadas", description="Define o canal público para os anúncios de compras aprovadas.")
async def set_canal_aprovadas(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_aprovadas_id
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    canal_aprovadas_id = canal.id
    await interaction.response.send_message(f"🎉 Canal de compras aprovadas configurado para {canal.mention}.", ephemeral=True)

@bot.tree.command(name="msg_fixa_auto", description="Configura uma mensagem fixa automática no final do chat com o botão.")
@app_commands.describe(canal="Canal alvo", texto="Texto da mensagem fixa")
async def msg_fixa_auto(interaction: discord.Interaction, canal: discord.TextChannel, texto: str):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    await interaction.response.send_message(f"✅ Mensagem automática fixada no canal {canal.mention}!", ephemeral=True)
    
    view_automatica = discord.ui.View()
    view_automatica.add_item(discord.ui.Button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True))

    msg = await canal.send(content=texto, view=view_automatica)
    canais_mensagem_fixa[canal.id] = {"texto": texto, "id_mensagem": msg.id}

@bot.tree.command(name="reag_auto", description="Configura auto-reação em um canal.")
async def reag_auto(interaction: discord.Interaction, canal: discord.TextChannel, emoji: str):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
    canais_reacao_auto[canal.id] = emoji
    await interaction.response.send_message(f"✅ Auto-reação configurada no canal {canal.mention} com o emoji {emoji}!", ephemeral=True)

# ================= CRIAÇÃO E EDIÇÃO DE PAINÉIS =================

@bot.tree.command(name="criar_painel", description="Cria um novo painel de vendas no canal selecionado.")
async def criar_painel(interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, descricao: str, estoque: int, preco: float, foto: str = None):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.blue())
    embed.add_field(name="📦 Estoque", value=f"`{estoque}` disponíveis", inline=True)
    embed.add_field(name="💵 Valor Unitário", value=f"R$ `{preco:.2f}`", inline=True)
    if foto and foto.startswith("http"): 
        embed.set_image(url=foto)

    msg = await canal.send(embed=embed, view=BotaoAbrirCarrinho())
    paineis_produtos[msg.id] = {
        "titulo": titulo, 
        "descricao": descricao, 
        "estoque": estoque, 
        "preco": preco, 
        "foto": foto, 
        "canal_id": canal.id
    }
    await interaction.response.send_message(f"✅ Painel criado com sucesso! ID da mensagem: `{msg.id}`.", ephemeral=True)

@bot.tree.command(name="editar_painel", description="Edita um painel ou mensagem existente informando o ID da mensagem.")
@app_commands.describe(
    msg_id="ID da mensagem do painel", 
    novo_titulo="Novo título", 
    nova_descricao="Nova descrição", 
    novo_estoque="Novo estoque", 
    novo_preco="Novo preço", 
    nova_foto="Novo link de foto"
)
async def editar_painel(
    interaction: discord.Interaction, 
    msg_id: str, 
    novo_titulo: str = None, 
    nova_descricao: str = None, 
    novo_estoque: int = None, 
    novo_preco: float = None, 
    nova_foto: str = None
):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    try:
        msg_id_int = int(msg_id)
    except ValueError:
        return await interaction.response.send_message("❌ O ID informado deve ser numérico.", ephemeral=True)

    mensagem_alvo = None
    for channel in interaction.guild.text_channels:
        try:
            mensagem_alvo = await channel.fetch_message(msg_id_int)
            break
        except:
            continue

    if not mensagem_alvo or not mensagem_alvo.embeds:
        return await interaction.response.send_message("❌ Mensagem ou Embed não encontrado com este ID.", ephemeral=True)

    embed_antigo = mensagem_alvo.embeds[0]
    titulo = novo_titulo if novo_titulo is not None else embed_antigo.title
    descricao = nova_descricao if nova_descricao is not None else embed_antigo.description
    
    if msg_id_int in paineis_produtos:
        p_info = paineis_produtos[msg_id_int]
        if novo_titulo is not None: p_info["titulo"] = novo_titulo
        if nova_descricao is not None: p_info["descricao"] = nova_descricao
        if novo_estoque is not None: p_info["estoque"] = novo_estoque
        if novo_preco is not None: p_info["preco"] = novo_preco
        if nova_foto is not None: p_info["foto"] = nova_foto if nova_foto.lower() != "nenhuma" else None

    embed_novo = discord.Embed(title=titulo, description=descricao, color=embed_antigo.color or discord.Color.blue())
    
    if msg_id_int in paineis_produtos:
        p_info = paineis_produtos[msg_id_int]
        embed_novo.add_field(name="📦 Estoque", value=f"`{p_info['estoque']}` disponíveis", inline=True)
        embed_novo.add_field(name="💵 Valor Unitário", value=f"R$ `{p_info['preco']:.2f}`", inline=True)
        if p_info["foto"]:
            embed_novo.set_image(url=p_info["foto"])
    else:
        for field in embed_antigo.fields:
            embed_novo.add_field(name=field.name, value=field.value, inline=field.inline)
        if nova_foto:
            embed_novo.set_image(url=nova_foto if nova_foto.lower() != "nenhuma" else None)
        elif embed_antigo.image:
            embed_novo.set_image(url=embed_antigo.image.url)

    try:
        if msg_id_int in paineis_produtos:
            await mensagem_alvo.edit(embed=embed_novo, view=BotaoAbrirCarrinho())
        else:
            await mensagem_alvo.edit(embed=embed_novo)
            
        await interaction.response.send_message("✅ Painel editado com sucesso!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao editar painel: {e}", ephemeral=True)

# ================= COMANDOS DE VENDA, APROVAÇÃO E COMPRA FAKE =================

@bot.tree.command(name="compra_fake", description="Gera um anúncio de compra aprovada FAKE no canal de aprovadas.")
async def compra_fake(interaction: discord.Interaction, usuario: discord.User, produto: str, quantidade: int, valor_pago: float):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    if not canal_aprovadas_id:
        return await interaction.response.send_message("❌ Canal de aprovadas não configurado. Use /set_canal_aprovadas.", ephemeral=True)

    c_aprovadas = interaction.guild.get_channel(canal_aprovadas_id)
    if not c_aprovadas:
        return await interaction.response.send_message("❌ Canal de aprovadas não encontrado no servidor.", ephemeral=True)

    avatar_url = usuario.display_avatar.url if usuario.avatar else bot.user.display_avatar.url

    desc_embed = (
        f"👤 **Cliente:** {usuario.mention}\n\n"
        f"📦 **Produto:** `{produto}`\n\n"
        f"🔢 **Quantidade:** `{quantidade}x`\n\n"
        f"♻️ **VALOR PAGO:** `R$ {valor_pago:.2f}`\n\n"
        f"✨ *O produto foi entregue automaticamente com segurança via Mensagem Direta (DM)!*"
    )

    embed_grande = discord.Embed(
        title=mensagens_sistema["embed_aprovada_titulo"],
        description=desc_embed,
        color=discord.Color.brand_green(),
        timestamp=datetime.now()
    )
    embed_grande.set_author(name=f"Cliente: {usuario.name}", icon_url=avatar_url)
    embed_grande.set_thumbnail(url=avatar_url)
    
    await c_aprovadas.send(embed=embed_grande)
    await interaction.response.send_message("✅ Embed de compra fake enviado com sucesso!", ephemeral=True)

@bot.tree.command(name="mandar_pix", description="Envia os dados de pagamento PIX dentro do carrinho.")
async def mandar_pix(interaction: discord.Interaction, chave: str = None):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    canal_id = interaction.channel.id
    if canal_id not in dados_carrinhos:
        return await interaction.response.send_message(mensagens_sistema["msg_fora_de_carrinho"], ephemeral=True)
        
    carrinhos_aguardando_pix[canal_id] = True
    chave_usar = chave if chave else chave_pix_global
    info_carrinho = dados_carrinhos[canal_id]
    total_pagar = info_carrinho["preco"] * info_carrinho["qtd"]
    
    await interaction.response.send_message(mensagens_sistema["pix_enviado"], ephemeral=True)
    texto_resumo = formatar_texto(
        mensagens_sistema["alerta_pix_carrinho"], 
        produto_nome=info_carrinho["produto_nome"], 
        qtd=info_carrinho["qtd"], 
        total=f"{total_pagar:.2f}", 
        chave=chave_usar
    )
    await interaction.channel.send(texto_resumo)
    
    # Log de envio de PIX
    embed_log = discord.Embed(
        title="💳 PIX ENVIADO NO CARRINHO", 
        description=f"**Canal:** {interaction.channel.mention}\n**Produto:** `{info_carrinho['produto_nome']}`\n**Valor:** R$ `{total_pagar:.2f}`", 
        color=discord.Color.gold(), 
        timestamp=datetime.now()
    )
    await enviar_log(interaction.guild, embed_log)

@bot.tree.command(name="aprovar", description="Aprova a compra no carrinho, entrega o produto e atualiza os canais.")
async def aprovar(interaction: discord.Interaction, produto: str):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    canal_id = interaction.channel.id
    if canal_id not in dados_carrinhos:
        return await interaction.response.send_message(mensagens_sistema["msg_fora_de_carrinho"], ephemeral=True)

    info_carrinho = dados_carrinhos[canal_id]
    cliente_id = info_carrinho["cliente_id"]
    qtd = info_carrinho["qtd"]
    panel_id = info_carrinho["panel_id"]
    nome_produto = info_carrinho["produto_nome"]
    total_venda = info_carrinho["preco"] * qtd

    historico_vendas.append({
        "valor": total_venda, 
        "qtd": qtd, 
        "produto": nome_produto, 
        "data": datetime.now()
    })

    cliente = await bot.fetch_user(cliente_id)

    # Atualiza o estoque do painel
    if panel_id in paineis_produtos:
        paineis_produtos[panel_id]["estoque"] = max(0, paineis_produtos[panel_id]["estoque"] - qtd)
        try:
            canal_p = interaction.guild.get_channel(paineis_produtos[panel_id]["canal_id"])
            if canal_p:
                msg_p = await canal_p.fetch_message(panel_id)
                p_i = paineis_produtos[panel_id]
                em = discord.Embed(title=p_i["titulo"], description=p_i["descricao"], color=discord.Color.blue())
                em.add_field(name="📦 Estoque", value=f"`{p_i['estoque']}` disponíveis", inline=True)
                em.add_field(name="💵 Valor Unitário", value=f"R$ `{p_i['preco']:.2f}`", inline=True)
                if p_i["foto"]: 
                    em.set_image(url=p_i["foto"])
                await msg_p.edit(embed=em, view=BotaoAbrirCarrinho())
        except: 
            pass

    carrinhos_aprovados.add(canal_id)
    await interaction.response.send_message(f"✅ Venda aprovada com sucesso! R$ `{total_venda:.2f}` registrados.", ephemeral=True)
    await interaction.channel.send(mensagens_sistema["compra_aprovada"])

    # Tenta enviar o produto na DM do cliente
    try:
        await cliente.send(formatar_texto(mensagens_sistema["dm_produto_entregue"], produto_nome=nome_produto, produto=produto))
    except:
        await interaction.channel.send(formatar_texto(mensagens_sistema["dm_fechada_aviso"], cliente=cliente.mention))

    # Anúncio no canal público de Aprovadas
    if canal_aprovadas_id:
        c_aprovadas = interaction.guild.get_channel(canal_aprovadas_id)
        if c_aprovadas:
            avatar = cliente.display_avatar.url if cliente.avatar else bot.user.display_avatar.url
            
            desc_embed_apv = (
                f"👤 **Cliente:** {cliente.mention}\n\n"
                f"📦 **Produto:** `{nome_produto}`\n\n"
                f"🔢 **Quantidade:** `{qtd}x`\n\n"
                f"♻️ **VALOR PAGO:** `R$ {total_venda:.2f}`\n\n"
                f"✨ *O produto foi entregue automaticamente com segurança via Mensagem Direta (DM)!*"
            )

            embed_apv = discord.Embed(
                title=mensagens_sistema["embed_aprovada_titulo"],
                description=desc_embed_apv,
                color=discord.Color.brand_green(),
                timestamp=datetime.now()
            )
            embed_apv.set_author(name=f"Cliente: {cliente.name}", icon_url=avatar)
            embed_apv.set_thumbnail(url=avatar)
            
            await c_aprovadas.send(embed=embed_apv)

            async def ping_feedback():
                msg = await c_aprovadas.send(formatar_texto(mensagens_sistema["msg_feedback_ping"], cliente=cliente.mention))
                await asyncio.sleep(10)
                try: 
                    await msg.delete()
                except: 
                    pass
            asyncio.create_task(ping_feedback())

    # Log de compra aprovada
    embed_log_aprovada = discord.Embed(
        title="🎉 COMPRA APROVADA",
        description=f"**Canal:** `{interaction.channel.name}`\n👤 **Cliente:** {cliente.mention}\n📦 **Produto:** `{nome_produto}`\n🔢 **Qtd:** `{qtd}`\n💰 **Total:** R$ `{total_venda:.2f}`",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    await enviar_log(interaction.guild, embed_log_aprovada)

    # Fechamento automático do carrinho
    async def fechar_carrinho():
        await asyncio.sleep(300)
        try:
            carrinhos_ativos_alerta.discard(canal_id)
            dados_carrinhos.pop(canal_id, None)
            await interaction.channel.delete()
        except: 
            pass
    asyncio.create_task(fechar_carrinho())

@bot.tree.command(name="rendimento", description="Exibe o painel financeiro de rendimentos em tempo real.")
async def rendimento(interaction: discord.Interaction):
    if not tem_permissao(interaction): 
        return await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)

    agora = datetime.now()
    total_faturamento = sum(v["valor"] for v in historico_vendas)
    faturamento_hoje = sum(v["valor"] for v in historico_vendas if v["data"].date() == agora.date())
    total_vendas = len(historico_vendas)
    total_itens = sum(v["qtd"] for v in historico_vendas)

    embed = discord.Embed(title="📊 PAINEL DE RENDIMENTO FINANCEIRO", color=discord.Color.gold(), timestamp=agora)
    embed.add_field(name="💰 Total Arrecadado", value=f"R$ `{total_faturamento:.2f}`", inline=True)
    embed.add_field(name="📅 Faturamento Hoje", value=f"R$ `{faturamento_hoje:.2f}`", inline=True)
    embed.add_field(name="📦 Total de Vendas", value=f"`{total_vendas}`", inline=True)
    embed.add_field(name="🔢 Unidades Vendidas", value=f"`{total_itens}`", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= INTERFACES (BOTÕES E MODAIS DO CARRINHO) =================

class BotaoAbrirCarrinho(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.btn_compra.label = mensagens_sistema["btn_abrir_carrinho"]

    @discord.ui.button(label="🛒 Comprar", style=discord.ButtonStyle.green, custom_id="btn_abrir")
    async def btn_compra(self, interaction: discord.Interaction, button: discord.ui.Button):
        panel_id = interaction.message.id
        painel_info = paineis_produtos.get(panel_id)

        if painel_info and painel_info["estoque"] <= 0: 
            return await interaction.response.send_message(mensagens_sistema["sem_estoque"], ephemeral=True)

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False), 
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Garante permissão para TODOS os donos adicionados verem os carrinhos
        for d in donos_permitidos:
            dm = guild.get_member(d)
            if dm: 
                overwrites[dm] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        cc = await guild.create_text_channel(
            name=f"🛒-carrinho-{interaction.user.name}", 
            category=interaction.channel.category, 
            overwrites=overwrites
        )
        await interaction.response.send_message(formatar_texto(mensagens_sistema["carrinho_aberto_sucesso"], canal=cc.mention), ephemeral=True)

        nome, preco = (painel_info["titulo"], painel_info["preco"]) if painel_info else ("Produto", 0.0)
        dados_carrinhos[cc.id] = {
            "cliente_id": interaction.user.id, 
            "qtd": 1, 
            "panel_id": panel_id, 
            "produto_nome": nome, 
            "preco": preco
        }

        await cc.send("@everyone")
        await cc.send(
            embed=discord.Embed(
                title=mensagens_sistema["embed_carrinho_titulo"], 
                description=formatar_texto(mensagens_sistema["embed_carrinho_desc"], produto_nome=nome, qtd=1), 
                color=discord.Color.light_grey()
            ), 
            view=InterfaceCarrinho(interaction.user.id)
        )

        # Log de Abertura de Carrinho
        embed_log_abertura = discord.Embed(
            title="🛒 CARRINHO ABERTO", 
            description=f"👤 **Cliente:** {interaction.user.mention}\n📦 **Produto:** `{nome}`\n📢 **Canal:** {cc.mention}", 
            color=discord.Color.blue(), 
            timestamp=datetime.now()
        )
        await enviar_log(guild, embed_log_abertura)

        carrinhos_ativos_alerta.add(cc.id)
        asyncio.create_task(alertar_dono_no_pv(cc.id, cc.name))

class ModalQuantidade(discord.ui.Modal, title="Alterar Quantidade"):
    qtd_in = discord.ui.TextInput(label="Digite a nova quantidade:", placeholder="Ex: 2", min_length=1, max_length=3)
    
    def __init__(self, c_id):
        super().__init__()
        self.c_id = c_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.qtd_in.value)
            if qtd <= 0: raise ValueError
        except: 
            return await interaction.response.send_message(mensagens_sistema["msg_quantidade_invalida"], ephemeral=True)

        cid = interaction.channel.id
        info = dados_carrinhos.get(cid, {})
        pid = info.get("panel_id")

        if pid in paineis_produtos and qtd > paineis_produtos[pid]["estoque"]:
            return await interaction.response.send_message(formatar_texto(mensagens_sistema["msg_estoque_insuficiente"], estoque=paineis_produtos[pid]["estoque"]), ephemeral=True)

        dados_carrinhos[cid]["qtd"] = qtd
        tot = info.get("preco", 0.0) * qtd
        desc = formatar_texto(mensagens_sistema["embed_carrinho_desc"], produto_nome=info.get("produto_nome", "Produto"), qtd=qtd) + f"\n\n💰 **Subtotal:** R$ `{tot:.2f}`"
        
        await interaction.response.edit_message(
            embed=discord.Embed(title=mensagens_sistema["embed_carrinho_titulo"], description=desc, color=discord.Color.green()), 
            view=InterfaceCarrinho(self.c_id)
        )

class InterfaceCarrinho(discord.ui.View):
    def __init__(self, c_id):
        super().__init__(timeout=None)
        self.c_id = c_id
        self.btn_conf.label = mensagens_sistema["btn_confirmar_compra"]
        self.btn_qtd.label = mensagens_sistema["btn_mudar_qtd"]
        self.btn_canc.label = mensagens_sistema["btn_cancelar_compra"]

    @discord.ui.button(label="COMPRA", style=discord.ButtonStyle.green, custom_id="c_conf")
    async def btn_conf(self, interaction: discord.Interaction, button: discord.ui.Button):
        carrinhos_ativos_alerta.discard(interaction.channel.id)
        await interaction.response.send_message(mensagens_sistema["msg_gerando_pix"])

    @discord.ui.button(label="QUANTIDADE", style=discord.ButtonStyle.primary, custom_id="c_qtd")
    async def btn_qtd(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.c_id: 
            return await interaction.response.send_message(mensagens_sistema["apenas_comprador"], ephemeral=True)
        await interaction.response.send_modal(ModalQuantidade(self.c_id))

    @discord.ui.button(label="CANCELA", style=discord.ButtonStyle.danger, custom_id="c_canc")
    async def btn_canc(self, interaction: discord.Interaction, button: discord.ui.Button):
        cid = interaction.channel.id
        nome_canal = interaction.channel.name
        carrinhos_ativos_alerta.discard(cid)

        # Log de Fechamento / Cancelamento de Carrinho
        embed_log_fechar = discord.Embed(
            title="❌ CARRINHO FECHADO / CANCELADO", 
            description=f"**Canal:** `{nome_canal}`\n**Fechado por:** {interaction.user.mention}", 
            color=discord.Color.red(), 
            timestamp=datetime.now()
        )
        await enviar_log(interaction.guild, embed_log_fechar)

        if cid in carrinhos_aprovados:
            await interaction.response.send_message(mensagens_sistema["compra_ja_realizada"])
            await asyncio.sleep(2)
            try: await interaction.channel.delete()
            except: pass
            return

        await interaction.response.send_message(mensagens_sistema["carrinho_cancelado"])
        await asyncio.sleep(2)
        try: 
            await interaction.channel.delete()
        except: 
            pass

if __name__ == "__main__":
    manter_online()
    bot.run(TOKEN_BOT)
