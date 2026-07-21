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
    # Pega a porta automática fornecida pelo Render ou usa 8080 por padrão
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
mensagem_automatica_task = None
carrinhos_aguardando_pix = {} 
dados_carrinhos = {} 

# Controle de alertas no PV
carrinhos_ativos_alerta = set()

config_painel = {
    "titulo": "Produto à Venda",
    "descricao": "Clique no botão abaixo para comprar.",
    "foto": None,
    "estoque": 0,
    "preco": 0.0, 
    "chave_pix": "Não configurada"
}

def tem_permissao(interaction: discord.Interaction):
    return interaction.user.id in donos_permitidos

async def enviar_log(guild, mensagem_embed):
    if canal_logs_id:
        canal = guild.get_channel(canal_logs_id)
        if canal:
            await canal.send(embed=mensagem_embed)

@bot.event
async def on_ready():
    print(f"🟢 {bot.user.name} está rodando com todas as funções atualizadas!")

@bot.event
async def on_message(message):
    # Se o dono responder dentro do canal do carrinho, para os alertas daquele carrinho
    if message.guild and message.author.id in donos_permitidos:
        if message.channel.id in carrinhos_ativos_alerta:
            carrinhos_ativos_alerta.discard(message.channel.id)

# Loop de notificação insistente no PV do dono
async def alertar_dono_no_pv(canal_id, canal_nome):
    dono_id = donos_permitidos[0]
    try:
        dono = await bot.fetch_user(dono_id)
        while canal_id in carrinhos_ativos_alerta:
            await dono.send(f"⚠️ **EI ACORDA!** Tem carrinho aberto aguardando atendimento: `{canal_nome}`!\n*Envie uma mensagem no canal do carrinho para parar este alerta.*")
            await asyncio.sleep(5)
    except Exception as e:
        print(f"Erro ao enviar mensagem no PV: {e}")

# ================= COMANDOS ADMINISTRATIVOS =================

@bot.tree.command(name="status_bot", description="Altera o status de atividade (Assistindo) do bot.")
async def status_bot(interaction: discord.Interaction, texto: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=texto))
    await interaction.response.send_message(f"📺 Status do bot alterado para: *Assistindo {texto}*", ephemeral=True)

@bot.tree.command(name="status_vendas", description="Muda o status do bot (Bloqueia compras para manutenção).")
async def status_vendas(interaction: discord.Interaction, status: str):
    global status_sistema
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
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
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    config_painel["titulo"] = titulo
    config_painel["descricao"] = descricao
    config_painel["estoque"] = estoque
    config_painel["preco"] = preco
    
    if foto and (foto.startswith("http://") or foto.startswith("https://")):
        config_painel["foto"] = foto
    else:
        config_painel["foto"] = None
        
    await interaction.response.send_message("⚙️ Configurações salvas!", ephemeral=True)

@bot.tree.command(name="config_pix", description="Configura a chave PIX padrão.")
async def config_pix(interaction: discord.Interaction, chave: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    config_painel["chave_pix"] = chave
    await interaction.response.send_message(f"✅ Chave PIX definida: `{chave}`", ephemeral=True)

@bot.tree.command(name="logs", description="Define o canal onde serão enviados os logs de carrinhos e compras.")
async def config_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    global canal_logs_id
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    canal_logs_id = canal.id
    await interaction.response.send_message(f"📢 Canal de logs profissionais definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="enviar_painel", description="Envia o painel com botão de compra.")
async def enviar_painel(interaction: discord.Interaction, canal: discord.TextChannel):
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    
    embed = discord.Embed(title=config_painel["titulo"], description=config_painel["descricao"], color=discord.Color.blue())
    embed.add_field(name="📦 Estoque", value=f"`{config_painel['estoque']}` disponíveis", inline=True)
    embed.add_field(name="💵 Valor Unitário", value=f"R$ `{config_painel['preco']:.2f}`", inline=True)
    
    if config_painel["foto"]:
        embed.set_image(url=config_painel["foto"])
        
    await canal.send(embed=embed, view=BotaoAbrirCarrinho())
    await interaction.response.send_message("✅ Painel publicado com sucesso!", ephemeral=True)

@bot.tree.command(name="mandar_pix", description="Envia o PIX calculado baseado na quantidade do carrinho.")
async def mandar_pix(interaction: discord.Interaction, chave: str = None):
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    
    canal_id = interaction.channel.id
    carrinhos_aguardando_pix[canal_id] = True 
    
    chave_usar = chave if chave else config_painel["chave_pix"]
    info_carrinho = dados_carrinhos.get(canal_id, {"qtd": 1})
    qtd = info_carrinho["qtd"]
    total_pagar = config_painel["preco"] * qtd
    
    await interaction.response.send_message("✅ PIX enviado!", ephemeral=True)
    await interaction.channel.send(f"⚠️ **AVISO:** Seu pedido está pronto.\n\n📊 **RESUMO INTELIGENTE:**\n📦 **Quantidade:** {qtd}x\n💰 **Valor Total:** R$ `{total_pagar:.2f}`\n\n🔑 **Chave PIX:** `{chave_usar}`\n\n*entrega automática.*")

@bot.tree.command(name="aprovar", description="Aprova a compra deste carrinho, baixa o estoque do painel e entrega o produto.")
async def aprovar(interaction: discord.Interaction, produto: str):
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    
    canal_id = interaction.channel.id
    
    if canal_id not in dados_carrinhos:
        await interaction.response.send_message("❌ Este comando só pode ser usado dentro de um canal de carrinho ativo!", ephemeral=True)
        return
        
    info_carrinho = dados_carrinhos[canal_id]
    cliente_id = info_carrinho["cliente_id"]
    qtd_comprada = info_carrinho["qtd"]

    cliente = await bot.fetch_user(cliente_id)

    if config_painel["estoque"] >= qtd_comprada:
        config_painel["estoque"] -= qtd_comprada
    else:
        config_painel["estoque"] = 0

    await interaction.response.send_message(f"✅ Venda aprovada! O estoque do painel foi atualizado.", ephemeral=True)
    await interaction.channel.send(f"🎉 **COMPRA APROVADA!!** O produto foi enviado na DM de {cliente.mention}! Obrigado pela preferência! ✨\n\n⏳ *O carrinho fechará em breve.*")
    
    try:
        await cliente.send(f"🎁 **Sua compra foi aprovada!**\n📦 Aqui está seu produto:\n`{produto}`")
    except:
        try: await interaction.channel.send(f"⚠️ {cliente.mention}, sua DM está fechada! Abra para receber.")
        except: pass

    embed_log = discord.Embed(title="💰 VENDA REALIZADA", color=discord.Color.green(), timestamp=datetime.now())
    embed_log.add_field(name="Cliente", value=cliente.mention)
    embed_log.add_field(name="Qtd Comprada", value=f"`{qtd_comprada}`")
    embed_log.add_field(name="Estoque Restante no Painel", value=f"`{config_painel['estoque']}`")
    await enviar_log(interaction.guild, embed_log)

    async def fechar_carrinho_breve():
        await asyncio.sleep(10)
        try:
            carrinhos_ativos_alerta.discard(canal_id)
            dados_carrinhos.pop(canal_id, None)
            await interaction.channel.delete()
        except: pass
    asyncio.create_task(fechar_carrinho_breve())

@bot.tree.command(name="anuncio_auto", description="Loop de anúncios que se auto-apagam e enviam 1 única mensagem a cada 3 horas.")
async def anuncio_auto(interaction: discord.Interaction, canal: discord.TextChannel, mensagem: str, status: str):
    global mensagem_automatica_task
    if not tem_permissao(interaction):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return

    # Cancelar anúncio ativo
    if status.lower() == "desativar":
        if mensagem_automatica_task and not mensagem_automatica_task.done():
            mensagem_automatica_task.cancel()
            mensagem_automatica_task = None
            await interaction.response.send_message("🛑 Divulgação automática parada com sucesso.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Não há nenhum anúncio automático ativo no momento.", ephemeral=True)
        return

    # Cancela task anterior se já existir uma rodando antes de criar a nova
    if mensagem_automatica_task and not mensagem_automatica_task.done():
        mensagem_automatica_task.cancel()

    await interaction.response.send_message(f"🔄 Anúncio automático configurado em {canal.mention}!", ephemeral=True)

    async def loop_anuncio():
        msg_anterior = None
        while True:
            try:
                # Deleta a mensagem anterior antes de postar a nova
                if msg_anterior:
                    try: await msg_anterior.delete()
                    except: pass

                # Embed Profissional de Anúncio
                embed_anuncio = discord.Embed(
                    title="📢 MENSAGEM DO SISTEMA",
                    description=mensagem,
                    color=discord.Color.gold(),
                    timestamp=datetime.now()
                )
                embed_anuncio.set_footer(text="Anúncio Automático • Atualizado a cada 3 horas")

                msg_anterior = await canal.send(embed=embed_anuncio)
                await asyncio.sleep(10800)  # Espera exatamente 3 horas (10800 segundos)
            except asyncio.CancelledError:
                if msg_anterior:
                    try: await msg_anterior.delete()
                    except: pass
                break
            except Exception as e:
                print(f"Erro no anúncio automático: {e}")
                await asyncio.sleep(60)

    mensagem_automatica_task = asyncio.create_task(loop_anuncio())

# ================= INTERFACES E BOTÕES =================

class BotaoAbrirCarrinho(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Comprar", style=discord.ButtonStyle.green, custom_id="abrir_carrinho_btn")
    async def comprar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if status_sistema == "upando":
            await interaction.response.send_message("❌ **Contas sendo upadas**, aguarde a finalização!", ephemeral=True)
            return
        if config_painel["estoque"] <= 0:
            await interaction.response.send_message("❌ Produto sem estoque no momento.", ephemeral=True)
            return

        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        canal_carrinho = await guild.create_text_channel(
            name=f"🛒-carrinho-{interaction.user.name}",
            category=interaction.channel.category,
            overwrites=overwrites
        )
        await interaction.response.send_message(f"✅ Carrinho aberto: {canal_carrinho.mention}", ephemeral=True)
        
        dados_carrinhos[canal_carrinho.id] = {"cliente_id": interaction.user.id, "qtd": 1}

        # Notifica o Everyone no canal do carrinho recém-criado
        await canal_carrinho.send("@everyone")

        embed_carrinho = discord.Embed(
            title="🛒 Painel do Carrinho",
            description="Use os botões abaixo para gerenciar seu pedido.\n\n📦 **Quantidade atual:** `1x`",
            color=discord.Color.light_grey()
        )
        await canal_carrinho.send(embed=embed_carrinho, view=InterfaceCarrinho(interaction.user.id))

        # LOG DE ABERTURA DE CARRINHO
        embed_log = discord.Embed(title="🛒 CARRINHO ABERTO", color=discord.Color.blue(), timestamp=datetime.now())
        embed_log.add_field(name="Cliente", value=interaction.user.mention)
        embed_log.add_field(name="Canal", value=canal_carrinho.mention)
        await enviar_log(guild, embed_log)

        # Inicia os alertas no PV do dono
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
            await interaction.response.send_message("❌ Digite um número válido maior que 0!", ephemeral=True)
            return

        if qtd > config_painel["estoque"]:
            await interaction.response.send_message(f"❌ Estoque insuficiente! Temos apenas `{config_painel['estoque']}` disponíveis.", ephemeral=True)
            return

        canal_id = interaction.channel.id
        dados_carrinhos[canal_id]["qtd"] = qtd
        total = config_painel["preco"] * qtd

        embed_atualizado = discord.Embed(
            title="🛒 Painel do Carrinho",
            description=f"Gerencie seu pedido abaixo.\n\n📦 **Quantidade selecionada:** `{qtd}x` unidades.\n💰 **Subtotal:** R$ `{total:.2f}`",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed_atualizado, view=InterfaceCarrinho(self.comprador_id))

class InterfaceCarrinho(discord.ui.View):
    def __init__(self, comprador_id):
        super().__init__(timeout=None)
        self.comprador_id = comprador_id

    @discord.ui.button(label="COMPRA", style=discord.ButtonStyle.green, custom_id="btn_confirmar_compra")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ *Aguarde uns instantes gerando PIX...*")
        canal_id = interaction.channel.id
        carrinhos_aguardando_pix[canal_id] = False 
        carrinhos_ativos_alerta.discard(canal_id)

    @discord.ui.button(label="🔢 QUANTIDADE", style=discord.ButtonStyle.primary, custom_id="btn_mudar_quantidade")
    async def mudar_qtd(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.comprador_id:
            await interaction.response.send_message("❌ Apenas quem abriu o carrinho pode mudar isso.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalQuantidade(self.comprador_id))

    @discord.ui.button(label="CANCELA", style=discord.ButtonStyle.danger, custom_id="btn_cancelar_compra")
    async def cancela(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal_id = interaction.channel.id
        carrinhos_ativos_alerta.discard(canal_id)
        
        # LOG DE CANCELAMENTO MANUAL
        embed_log = discord.Embed(title="❌ CARRINHO CANCELADO", color=discord.Color.red(), timestamp=datetime.now())
        embed_log.add_field(name="Quem cancelou", value=interaction.user.mention)
        embed_log.add_field(name="Canal", value=f"`{interaction.channel.name}`")
        await enviar_log(interaction.guild, embed_log)

        await interaction.response.send_message("❌ Cancelando e fechando...")
        await asyncio.sleep(2)
        try: await interaction.channel.delete()
        except: pass

if __name__ == "__main__":
    manter_online() 
    bot.run(TOKEN_BOT)
