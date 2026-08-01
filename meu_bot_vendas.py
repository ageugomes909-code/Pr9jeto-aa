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
carrinhos_aguardando_pix = {}
dados_carrinhos = {}
carrinhos_aprovados = set()
carrinhos_ativos_alerta = set()

# Controle de Anúncio Automático
canal_anuncio_id = None
texto_anuncio_auto = None
msg_anuncio_anterior = None

# BANCO TOTAL DE TEXTOS, EMBEDS E BOTÕES DO BOT (100% DINÂMICO)
mensagens_sistema = {
    # Alertas e Respostas do Sistema
    "sem_permissao": "❌ Sem permissão.",
    "apenas_comprador": "❌ Apenas quem abriu o carrinho pode mudar isso.",
    "bot_travado": "❌ **Contas sendo upadas**, aguarde a finalização!",
    "sem_estoque": "❌ Produto sem estoque no momento.",
    "compra_aprovada": "🎉 **COMPRA APROVADA!!** O produto foi enviado na sua DM! Obrigado pela preferência! ✨\n\n⏳ *O carrinho fechará automaticamente em 5 minutos.*",
    "carrinho_cancelado": "❌ Cancelando e fechando...",
    "pix_enviado": "✅ PIX enviado!",
    "compra_ja_realizada": "🎉 **COMPRA REALIZADA COM SUCESSO!** Fechando carrinho...",
    "alerta_pix_carrinho": "⚠️ **AVISO:** Seu pedido está pronto.\n\n📊 **RESUMO INTELIGENTE:**\n📦 **Quantidade:** {qtd}x\n💰 **Valor Total:** R$ `{total}`\n\n🔑 **Chave PIX:** `{chave}`\n\n*entrega automática.*",
    "dm_produto_entregue": "🎁 **Sua compra foi aprovada!**\n📦 Aqui está seu produto:\n`{produto}`",
    "dm_fechada_aviso": "⚠️ {cliente}, sua DM está fechada! Abra para receber.",
    "msg_feedback_ping": "⚠️ {cliente}, por favor dê seu feedback sobre a compra!",
    "msg_quantidade_invalida": "❌ Digite um número válido maior que 0!",
    "msg_estoque_insuficiente": "❌ Estoque insuficiente! Temos apenas `{estoque}` disponíveis.",
    "msg_fora_de_carrinho": "❌ Este comando só pode ser usado dentro de um canal de carrinho ativo!",
    "aviso_alerta_pv": "⚠️ EI ACORDA! Tem carrinho aberto aguardando atendimento: {canal_nome}!\nEnvie uma mensagem no canal do carrinho para parar este alerta.",
    "msg_gerando_pix": "⏳ *Aguarde uns instantes gerando PIX...*",
    "carrinho_aberto_sucesso": "✅ Carrinho aberto: {canal}",

    # Embeds
    "embed_carrinho_titulo": "🛒 Painel do Carrinho",
    "embed_carrinho_desc": "Use os botões abaixo para gerenciar seu pedido.\n\n📦 **Quantidade atual:** `{qtd}x`",
    "embed_aprovada_titulo": "🛒 COMPRA APROVADA!",
    "embed_aprovada_rodape": "Obrigado pela preferência!",

    # Botões
    "btn_abrir_carrinho": "🛒 Comprar",
    "btn_confirmar_compra": "COMPRA",
    "btn_mudar_qtd": "🔢 QUANTIDADE",
    "btn_cancelar_compra": "CANCELA"
}

config_painel = {
    "titulo": "Produto à Venda",
    "descricao": "Clique no botão abaixo para comprar.",
    "foto": None,
    "estoque": 0,
    "preco": 0.0,
    "chave_pix": "Não configurada",
    "canal_painel_id": None,
    "msg_painel_id": None
}

def tem_permissao(interaction: discord.Interaction):
    return interaction.user.id in donos_permitidos

def formatar_texto(template: str, **kwargs):
    """Substitui tags no texto de forma segura"""
    try:
        return template.format(**kwargs)
    except Exception:
        return template

async def enviar_log(guild, mensagem_embed):
    global canal_logs_id
    if canal_logs_id:
        canal = guild.get_channel(canal_logs_id)
        if not canal:
            try:
                canal = await guild.fetch_channel(canal_logs_id)
            except:
                canal = None
        if canal:
            await canal.send(embed=mensagem_embed)

async def atualizar_embed_painel(guild):
    """Atualiza a mensagem pública do painel com o estoque correto"""
    if config_painel["canal_painel_id"] and config_painel["msg_painel_id"]:
        try:
            canal = guild.get_channel(config_painel["canal_painel_id"])
            if canal:
                msg = await canal.fetch_message(config_painel["msg_painel_id"])
                embed = discord.Embed(title=config_painel["titulo"], description=config_painel["descricao"], color=discord.Color.blue())
                embed.add_field(name="📦 Estoque", value=f"`{config_painel['estoque']}` disponíveis", inline=True)
                embed.add_field(name="💵 Valor Unitário", value=f"R$ `{config_painel['preco']:.2f}`", inline=True)
                if config_painel["foto"]:
                    embed.set_image(url=config_painel["foto"])
                await msg.edit(embed=embed, view=BotaoAbrirCarrinho())
        except Exception as e:
            print(f"Erro ao atualizar embed do painel: {e}")

@bot.event
async def on_ready():
    print(f"🟢 {bot.user.name} online com 100% dos textos centralizados e editáveis!")

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

# ================= VIEWS E BOTÕES ESPECIAIS =================

class ViewMensagemAutomatica(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_msg_auto_disabled")
    async def btn_auto(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

# ================= SISTEMA DE EDIÇÃO DE MENSAGENS =================

class ModalEditarMensagem(discord.ui.Modal):
    def __init__(self, chave_msg):
        super().__init__(title="Editar Texto/Botão do Bot")
        self.chave_msg = chave_msg
        self.texto_input = discord.ui.TextInput(
            label="Novo Texto",
            style=discord.TextStyle.paragraph,
            default=mensagens_sistema[chave_msg],
            required=True
        )
        self.add_item(self.texto_input)

    async def on_submit(self, interaction: discord.Interaction):
        mensagens_sistema[self.chave_msg] = self.texto_input.value
        await interaction.response.send_message(f"✅ Item `{self.chave_msg}` atualizado com sucesso!", ephemeral=True)

class SelectMensagensView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        
    @discord.ui.select(
        placeholder="Selecione QUALQUER texto do bot para alterar...",
        options=[
            discord.SelectOption(label="Sem Permissão", value="sem_permissao", description="Falta de permissão de admin"),
            discord.SelectOption(label="Apenas Comprador", value="apenas_comprador", description="Acesso exclusivo no carrinho"),
            discord.SelectOption(label="Bot Travado", value="bot_travado", description="Aviso de vendas desativadas"),
            discord.SelectOption(label="Sem Estoque", value="sem_estoque", description="Aviso de falta de estoque"),
            discord.SelectOption(label="Compra Aprovada", value="compra_aprovada", description="Aviso no carrinho ao aprovar"),
            discord.SelectOption(label="Carrinho Cancelado", value="carrinho_cancelado", description="Mensagem ao fechar carrinho"),
            discord.SelectOption(label="PIX Enviado", value="pix_enviado", description="Confirmação de envio do PIX"),
            discord.SelectOption(label="Compra Já Realizada", value="compra_ja_realizada", description="Tentar cancelar carrinho já aprovado"),
            discord.SelectOption(label="Resumo PIX", value="alerta_pix_carrinho", description="Usa tags {qtd}, {total}, {chave}"),
            discord.SelectOption(label="Produto na DM", value="dm_produto_entregue", description="Usa tag {produto}"),
            discord.SelectOption(label="DM Fechada", value="dm_fechada_aviso", description="Usa tag {cliente}"),
            discord.SelectOption(label="Pedir Feedback", value="msg_feedback_ping", description="Mensagem 10s. Usa tag {cliente}"),
            discord.SelectOption(label="Qtd Inválida", value="msg_quantidade_invalida", description="Erro ao digitar quantidade"),
            discord.SelectOption(label="Estoque Insuficiente", value="msg_estoque_insuficiente", description="Usa tag {estoque}"),
            discord.SelectOption(label="Fora do Carrinho", value="msg_fora_de_carrinho", description="Erro ao aprovar fora do canal"),
            discord.SelectOption(label="Alerta no PV do Dono", value="aviso_alerta_pv", description="Usa tag {canal_nome}"),
            discord.SelectOption(label="Aguarde Gerando PIX", value="msg_gerando_pix", description="Mensagem ao clicar no botão COMPRA"),
            discord.SelectOption(label="Carrinho Aberto Sucesso", value="carrinho_aberto_sucesso", description="Usa tag {canal}"),
            discord.SelectOption(label="Embed Carrinho - Título", value="embed_carrinho_titulo", description="Título do embed do carrinho"),
            discord.SelectOption(label="Embed Carrinho - Descrição", value="embed_carrinho_desc", description="Usa tag {qtd}"),
            discord.SelectOption(label="Embed Aprovada - Título", value="embed_aprovada_titulo", description="Título do anúncio público"),
            discord.SelectOption(label="Botão: Abrir Carrinho", value="btn_abrir_carrinho", description="Rótulo do botão de compra público"),
            discord.SelectOption(label="Botão: Confirmar Compra", value="btn_confirmar_compra", description="Rótulo do botão COMPRA"),
            discord.SelectOption(label="Botão: Alterar Qtd", value="btn_mudar_qtd", description="Rótulo do botão QUANTIDADE"),
            discord.SelectOption(label="Botão: Cancelar Compra", value="btn_cancelar_compra", description="Rótulo do botão CANCELA")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        chave = select.values[0]
        await interaction.response.send_modal(ModalEditarMensagem(chave))

@bot.tree.command(name="config_mensagens", description="Painel para personalizar qualquer mensagem, embed ou botão do bot.")
async def config_mensagens(interaction: discord.Interaction):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    await interaction.response.send_message("⚙️ **Painel Geral de Personalização de Textos e Botões**\nEscolha o item que deseja alterar:", view=SelectMensagensView(), ephemeral=True)

# ================= COMANDO PARA ENVIAR MENSAGEM NO PV =================

@bot.tree.command(name="enviar_pv", description="Envia uma mensagem direta no PV de um usuário específico.")
async def enviar_pv(interaction: discord.Interaction, usuario: discord.User, mensagem: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    try:
        await usuario.send(mensagem)
        await interaction.response.send_message(f"✅ Mensagem enviada com sucesso no PV de {usuario.mention}!", ephemeral=True)
    except Exception:
        await interaction.response.send_message(f"❌ Não foi possível enviar mensagem para {usuario.mention}. A DM pode estar fechada.", ephemeral=True)

# ================= COMANDOS ADMINISTRATIVOS =================

@bot.tree.command(name="add_dono", description="Adiciona permissão a um usuário para usar comandos e gerenciar carrinhos.")
async def add_dono(interaction: discord.Interaction, usuario: discord.User):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    if usuario.id not in donos_permitidos:
        donos_permitidos.append(usuario.id)
        await interaction.response.send_message(f"✅ {usuario.mention} agora possui permissão administrativa no bot!", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Este usuário já possui permissão.", ephemeral=True)

@bot.tree.command(name="status_bot", description="Altera o status de atividade (Assistindo) do bot.")
async def status_bot(interaction: discord.Interaction, texto: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=texto))
    await interaction.response.send_message(f"📺 Status do bot alterado para: Assistindo {texto}", ephemeral=True)

@bot.tree.command(name="status_vendas", description="Muda o status do bot (Bloqueia compras para manutenção).")
async def status_vendas(interaction: discord.Interaction, status: str):
    global status_sistema
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    if status.lower() == "upando":
        status_sistema = "upando"
        await interaction.response.send_message("⚠️ Bot travado! Compras desativadas.", ephemeral=True)
    else:
        status_sistema = "normal"
        await interaction.response.send_message("✅ Bot liberado! Compras normais.", ephemeral=True)

@bot.tree.command(name="painel_config", description="Configura o painel principal.")
async def painel_config(interaction: discord.Interaction, titulo: str, descricao: str, estoque: int, preco: float, foto: str = None):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    config_painel["titulo"] = titulo
    config_painel["descricao"] = descricao
    config_painel["estoque"] = estoque
    config_painel["preco"] = preco

    if foto and (foto.startswith("http://") or foto.startswith("https://")):  
        config_painel["foto"] = foto  
    else:  
        config_painel["foto"] = None  
          
    await atualizar_embed_painel(interaction.guild)
    await interaction.response.send_message("⚙️ Configurações salvas e painel atualizado!", ephemeral=True)

@bot.tree.command(name="config_pix", description="Configura a chave PIX padrão.")
async def config_pix(interaction: discord.Interaction, chave: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    config_painel["chave_pix"] = chave
    await interaction.response.send_message(f"✅ Chave PIX definida: {chave}", ephemeral=True)

@bot.tree.command(name="logs", description="Define o canal onde serão enviados os logs de carrinhos e compras.")
async def config_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_logs_id
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    canal_logs_id = canal.id
    await interaction.response.send_message(f"📢 Canal de logs profissionais definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="set_canal_aprovadas", description="Define o canal público para anunciar compras aprovadas e pedir feedback.")
async def set_canal_aprovadas(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_aprovadas_id
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return
    canal_aprovadas_id = canal.id
    await interaction.response.send_message(f"🎉 Canal de anúncios de compras aprovadas e feedback definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="enviar_painel", description="Envia o painel com botão de compra.")
async def enviar_painel(interaction: discord.Interaction, canal: discord.TextChannel):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    embed = discord.Embed(title=config_painel["titulo"], description=config_painel["descricao"], color=discord.Color.blue())  
    embed.add_field(name="📦 Estoque", value=f"`{config_painel['estoque']}` disponíveis", inline=True)  
    embed.add_field(name="💵 Valor Unitário", value=f"R$ `{config_painel['preco']:.2f}`", inline=True)  
      
    if config_painel["foto"]:  
        embed.set_image(url=config_painel["foto"])  
          
    msg = await canal.send(embed=embed, view=BotaoAbrirCarrinho())  
    config_painel["canal_painel_id"] = canal.id
    config_painel["msg_painel_id"] = msg.id
    
    await interaction.response.send_message("✅ Painel publicado com sucesso!", ephemeral=True)

@bot.tree.command(name="mandar_pix", description="Envia o PIX calculado baseado na quantidade do carrinho.")
async def mandar_pix(interaction: discord.Interaction, chave: str = None):
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    canal_id = interaction.channel.id  
    carrinhos_aguardando_pix[canal_id] = True   
      
    chave_usar = chave if chave else config_painel["chave_pix"]  
    info_carrinho = dados_carrinhos.get(canal_id, {"qtd": 1})  
    qtd = info_carrinho["qtd"]  
    total_pagar = config_painel["preco"] * qtd  
      
    await interaction.response.send_message(mensagens_sistema["pix_enviado"], ephemeral=True)  
    
    texto_resumo_pix = formatar_texto(
        mensagens_sistema["alerta_pix_carrinho"],
        qtd=qtd,
        total=f"{total_pagar:.2f}",
        chave=chave_usar
    )
    await interaction.channel.send(texto_resumo_pix)

@bot.tree.command(name="aprovar", description="Aprova a compra deste carrinho, baixa o estoque do painel e entrega o produto.")
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

    cliente = await bot.fetch_user(cliente_id)  

    if config_painel["estoque"] >= qtd_comprada:  
        config_painel["estoque"] -= qtd_comprada  
    else:  
        config_painel["estoque"] = 0  
    
    await atualizar_embed_painel(interaction.guild)

    carrinhos_aprovados.add(canal_id)

    await interaction.response.send_message("✅ Venda aprovada! O estoque do painel foi atualizado.", ephemeral=True)  
    await interaction.channel.send(mensagens_sistema["compra_aprovada"])  
      
    try:  
        texto_dm = formatar_texto(mensagens_sistema["dm_produto_entregue"], produto=produto)
        await cliente.send(texto_dm)  
    except:  
        try: 
            texto_dm_fechada = formatar_texto(mensagens_sistema["dm_fechada_aviso"], cliente=cliente.mention)
            await interaction.channel.send(texto_dm_fechada)  
        except: pass  

    if canal_aprovadas_id:
        c_aprovadas = interaction.guild.get_channel(canal_aprovadas_id)
        if c_aprovadas:
            embed_aprovada = discord.Embed(
                title=mensagens_sistema["embed_aprovada_titulo"],
                description=f"🎉 **Cliente:** {cliente.mention}\n📦 **Produto:** `{produto}`\n🔢 **Quantidade:** `{qtd_comprada}x`",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            embed_aprovada.set_footer(text=mensagens_sistema["embed_aprovada_rodape"])
            await c_aprovadas.send(embed=embed_aprovada)

            async def marcar_e_apagar_feedback():
                texto_ping = formatar_texto(mensagens_sistema["msg_feedback_ping"], cliente=cliente.mention)
                msg_ping = await c_aprovadas.send(texto_ping)
                await asyncio.sleep(10)
                try: await msg_ping.delete()
                except: pass

            asyncio.create_task(marcar_e_apagar_feedback())

    embed_log = discord.Embed(title="💰 VENDA REALIZADA", color=discord.Color.green(), timestamp=datetime.now())  
    embed_log.add_field(name="Cliente", value=cliente.mention)  
    embed_log.add_field(name="Qtd Comprada", value=f"`{qtd_comprada}`")  
    embed_log.add_field(name="Estoque Restante no Painel", value=f"`{config_painel['estoque']}`")  
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

@bot.tree.command(name="anuncio_auto", description="Configura aviso automático no canal e re-envio inteligente ao enviarem mensagem.")
async def anuncio_auto(interaction: discord.Interaction, canal: discord.TextChannel, mensagem: str, status: str):
    global canal_anuncio_id, texto_anuncio_auto, msg_anuncio_anterior
    if not tem_permissao(interaction):
        await interaction.response.send_message(mensagens_sistema["sem_permissao"], ephemeral=True)
        return

    if status.lower() == "desativar":  
        canal_anuncio_id = None
        texto_anuncio_auto = None
        if msg_anuncio_anterior:
            try: await msg_anuncio_anterior.delete()
            except: pass
        msg_anuncio_anterior = None
        await interaction.response.send_message("🛑 Anúncio automático desativado com sucesso.", ephemeral=True)  
        return  

    canal_anuncio_id = canal.id
    texto_anuncio_auto = mensagem

    if msg_anuncio_anterior:
        try: await msg_anuncio_anterior.delete()
        except: pass

    embed_anuncio = discord.Embed(  
        description=mensagem,  
        color=discord.Color.gold(),  
        timestamp=datetime.now()  
    )  

    msg_anuncio_anterior = await canal.send(embed=embed_anuncio, view=ViewMensagemAutomatica())  
    await interaction.response.send_message(f"🔄 Anúncio automático configurado em {canal.mention}!", ephemeral=True)

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
        if config_painel["estoque"] <= 0:  
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
          
        dados_carrinhos[canal_carrinho.id] = {"cliente_id": interaction.user.id, "qtd": 1}  

        await canal_carrinho.send("@everyone")  

        desc_embed = formatar_texto(mensagens_sistema["embed_carrinho_desc"], qtd=1)
        embed_carrinho = discord.Embed(  
            title=mensagens_sistema["embed_carrinho_titulo"],  
            description=desc_embed,  
            color=discord.Color.light_grey()  
        )  
        await canal_carrinho.send(embed=embed_carrinho, view=InterfaceCarrinho(interaction.user.id))  

        embed_log = discord.Embed(title="🛒 CARRINHO ABERTO", color=discord.Color.blue(), timestamp=datetime.now())  
        embed_log.add_field(name="Cliente", value=interaction.user.mention)  
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

        if qtd > config_painel["estoque"]:  
            texto_insuf = formatar_texto(mensagens_sistema["msg_estoque_insuficiente"], estoque=config_painel["estoque"])
            await interaction.response.send_message(texto_insuf, ephemeral=True)  
            return  

        canal_id = interaction.channel.id  
        dados_carrinhos[canal_id]["qtd"] = qtd  
        total = config_painel["preco"] * qtd  

        desc_embed = formatar_texto(mensagens_sistema["embed_carrinho_desc"], qtd=qtd) + f"\n💰 **Subtotal:** R$ `{total:.2f}`"
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

