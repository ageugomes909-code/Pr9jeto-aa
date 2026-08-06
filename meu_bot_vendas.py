import discord
from discord import app_commands
import asyncio
from datetime import datetime
from flask import Flask
from threading import Thread
import os
import aiohttp

# ================= SERVER PARA MANTER ONLINE =================
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Online e Conectado ao Firebase!"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def manter_online(): Thread(target=run).start()

# ================= CONFIG FIREBASE (REST API) =================
FB_URL = "https://davi-xiter-default-rtdb.firebaseio.com"

async def ler_fb(caminho):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FB_URL}/{caminho}.json") as resp:
            return await resp.json() or {}

async def gravar_fb(caminho, dados):
    async with aiohttp.ClientSession() as session:
        async with session.put(f"{FB_URL}/{caminho}.json", json=dados) as resp:
            return await resp.json()

async def deletar_fb(caminho):
    async with aiohttp.ClientSession() as session:
        async with session.delete(f"{FB_URL}/{caminho}.json") as resp:
            return await resp.json()

# ================= VARIÁVEIS DE MEMÓRIA (CACHE) =================
donos_permitidos = [985441586898939904]
configs = {"canal_logs": None, "canal_aprovadas": None, "chave_pix": "Não configurada"}
paineis_produtos = {}  
historico_vendas = []  

# Dados temporários (não vão pro Firebase pois fecham rápido)
carrinhos_aguardando_pix = {}
dados_carrinhos = {}   
carrinhos_aprovados = set()
carrinhos_ativos_alerta = set()
canais_reacao_auto = {} 
canais_mensagem_fixa = {} 

# ================= SISTEMA DO BOT =================
TOKEN_BOT = os.getenv("DISCORD_TOKEN")

class MeuBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        print("Sincronizando com Firebase...")
        global configs, paineis_produtos, historico_vendas
        
        db_configs = await ler_fb("configs")
        db_paineis = await ler_fb("paineis")
        db_vendas = await ler_fb("vendas")
        
        if db_configs: configs.update(db_configs)
        if db_paineis: paineis_produtos.update({int(k): v for k, v in db_paineis.items()})
        if db_vendas: historico_vendas = list(db_vendas.values())

        await self.tree.sync()
        print("Comandos carregados. Bot pronto pro combate.")

bot = MeuBot()

def tem_permissao(interaction: discord.Interaction):
    return interaction.user.id in donos_permitidos

async def enviar_log(guild, embed):
    canal_id = configs.get("canal_logs")
    if canal_id:
        try:
            canal = guild.get_channel(int(canal_id))
            if not canal:
                canal = await guild.fetch_channel(int(canal_id))
            if canal:
                await canal.send(embed=embed)
        except Exception as e:
            print(f"Erro ao enviar log: {e}")

@bot.event
async def on_ready():
    print(f"🟢 {bot.user.name} online, bruto e rodando Firebase.")

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id: return

    # REAÇÃO AUTOMÁTICA
    if message.channel.id in canais_reacao_auto:
        try: await message.add_reaction(canais_reacao_auto[message.channel.id])
        except: pass

    # MENSAGEM FIXA (STICKY)
    if message.channel.id in canais_mensagem_fixa:
        dados_sticky = canais_mensagem_fixa[message.channel.id]
        if dados_sticky["id_mensagem"]:
            try:
                msg_antiga = await message.channel.fetch_message(dados_sticky["id_mensagem"])
                await msg_antiga.delete()
            except: pass 
        
        view_automatica = discord.ui.View()
        view_automatica.add_item(discord.ui.Button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True))
        try:
            nova_msg = await message.channel.send(content=dados_sticky["texto"], view=view_automatica)
            canais_mensagem_fixa[message.channel.id]["id_mensagem"] = nova_msg.id
        except: pass

    # DESATIVAR ALERTA DE CARRINHO
    if message.guild and message.author.id in donos_permitidos:
        carrinhos_ativos_alerta.discard(message.channel.id)

# ================= COMANDOS DE CHAT E DM =================

@bot.tree.command(name="enviar_pv", description="Envia uma mensagem direta (DM) para um usuário.")
async def enviar_pv(interaction: discord.Interaction, usuario: discord.User, texto: str):
    if not tem_permissao(interaction): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    try:
        await usuario.send(texto)
        await interaction.response.send_message(f"✅ Mensagem enviada para o PV de {usuario.mention}.", ephemeral=True)
    except:
        await interaction.response.send_message(f"❌ A DM de {usuario.mention} está fechada.", ephemeral=True)

@bot.tree.command(name="anuncio", description="Envia um Embed em um canal específico.")
async def anuncio(interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, descricao: str):
    if not tem_permissao(interaction): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.purple())
    await canal.send(embed=embed)
    await interaction.response.send_message("✅ Anúncio enviado.", ephemeral=True)

@bot.tree.command(name="limpar", description="Apaga mensagens do chat.")
async def limpar(interaction: discord.Interaction, quantidade: int):
    if not tem_permissao(interaction): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deletadas = await interaction.channel.purge(limit=quantidade)
    await interaction.followup.send(f"✅ `{len(deletadas)}` mensagens apagadas.")

# ================= COMANDOS DO SISTEMA AUTOMÁTICO =================

@bot.tree.command(name="msg_fixa_auto", description="Fixa uma mensagem automática no final do chat.")
async def msg_fixa_auto(interaction: discord.Interaction, canal: discord.TextChannel, texto: str):
    if not tem_permissao(interaction): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_message(f"✅ Fixado no {canal.mention}!", ephemeral=True)
    
    view_automatica = discord.ui.View()
    view_automatica.add_item(discord.ui.Button(label="Mensagem Automática", style=discord.ButtonStyle.secondary, disabled=True))
    msg = await canal.send(content=texto, view=view_automatica)
    canais_mensagem_fixa[canal.id] = {"texto": texto, "id_mensagem": msg.id}

@bot.tree.command(name="reag_auto", description="Configura auto-reação em um canal.")
async def reag_auto(interaction: discord.Interaction, canal: discord.TextChannel, emoji: str):
    if not tem_permissao(interaction): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    canais_reacao_auto[canal.id] = emoji
    await interaction.response.send_message(f"✅ Reação {emoji} no {canal.mention} ativada.", ephemeral=True)

# ================= CONFIGURAÇÕES E FIREBASE =================

@bot.tree.command(name="config_pix", description="Configura PIX.")
async def config_pix(interaction: discord.Interaction, chave: str):
    if not tem_permissao(interaction): return
    configs["chave_pix"] = chave
    asyncio.create_task(gravar_fb("configs", configs))
    await interaction.response.send_message(f"✅ Chave PIX: `{chave}`", ephemeral=True)

@bot.tree.command(name="logs", description="Define canal de logs.")
async def config_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    if not tem_permissao(interaction): return
    configs["canal_logs"] = canal.id
    asyncio.create_task(gravar_fb("configs", configs))
    await interaction.response.send_message(f"✅ Logs no {canal.mention}.", ephemeral=True)

@bot.tree.command(name="set_canal_aprovadas", description="Canal de compras finalizadas.")
async def set_canal_aprovadas(interaction: discord.Interaction, canal: discord.TextChannel):
    if not tem_permissao(interaction): return
    configs["canal_aprovadas"] = canal.id
    asyncio.create_task(gravar_fb("configs", configs))
    await interaction.response.send_message(f"✅ Aprovadas no {canal.mention}", ephemeral=True)

@bot.tree.command(name="add_dono", description="Adiciona permissão total.")
async def add_dono(interaction: discord.Interaction, usuario: discord.User):
    if not tem_permissao(interaction): return
    if usuario.id not in donos_permitidos: donos_permitidos.append(usuario.id)
    await interaction.response.send_message(f"✅ {usuario.mention} virou admin.", ephemeral=True)

@bot.tree.command(name="rendimento", description="Exibe o painel financeiro via Firebase.")
async def rendimento(interaction: discord.Interaction):
    if not tem_permissao(interaction): return
    agora = datetime.now()
    historico_valid = [{"valor": v["valor"], "qtd": v["qtd"], "data": datetime.fromisoformat(v["data"])} for v in historico_vendas if "data" in v]
    
    total_faturamento = sum(v["valor"] for v in historico_valid)
    faturamento_hoje = sum(v["valor"] for v in historico_valid if v["data"].date() == agora.date())
    
    embed = discord.Embed(title="📊 PAINEL DE RENDIMENTO FINANCEIRO", color=discord.Color.gold(), timestamp=agora)
    embed.add_field(name="💰 Total", value=f"R$ `{total_faturamento:.2f}`", inline=True)
    embed.add_field(name="📅 Hoje", value=f"R$ `{faturamento_hoje:.2f}`", inline=True)
    embed.add_field(name="📦 Vendas", value=f"`{len(historico_valid)}`", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= VENDAS E PAINÉIS =================

@bot.tree.command(name="criar_painel", description="Cria um painel de vendas no chat.")
async def criar_painel(interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, descricao: str, estoque: int, preco: float, foto: str = None):
    if not tem_permissao(interaction): return

    embed = discord.Embed(title=titulo, description=descricao, color=discord.Color.blue())
    embed.add_field(name="📦 Estoque", value=f"`{estoque}` disponíveis", inline=True)
    embed.add_field(name="💵 Valor Unitário", value=f"R$ `{preco:.2f}`", inline=True)
    if foto: embed.set_image(url=foto)

    msg = await canal.send(embed=embed, view=BotaoAbrirCarrinho())
    
    dados_painel = {"titulo": titulo, "descricao": descricao, "estoque": estoque, "preco": preco, "foto": foto, "canal_id": canal.id}
    paineis_produtos[msg.id] = dados_painel
    asyncio.create_task(gravar_fb(f"paineis/{msg.id}", dados_painel))
    
    await interaction.response.send_message(f"✅ Painel criado e salvo. ID: `{msg.id}`.", ephemeral=True)

@bot.tree.command(name="editar_painel", description="Edita painel e salva no banco.")
async def editar_painel(interaction: discord.Interaction, msg_id: str, novo_titulo: str = None, nova_descricao: str = None, novo_estoque: int = None, novo_preco: float = None):
    if not tem_permissao(interaction): return
    msg_id_int = int(msg_id)
    
    if msg_id_int not in paineis_produtos: return await interaction.response.send_message("❌ Painel não está no banco.", ephemeral=True)
    
    p_info = paineis_produtos[msg_id_int]
    if novo_titulo: p_info["titulo"] = novo_titulo
    if nova_descricao: p_info["descricao"] = nova_descricao
    if novo_estoque is not None: p_info["estoque"] = novo_estoque
    if novo_preco is not None: p_info["preco"] = novo_preco

    asyncio.create_task(gravar_fb(f"paineis/{msg_id_int}", p_info))
    
    try:
        canal = interaction.guild.get_channel(p_info["canal_id"])
        msg = await canal.fetch_message(msg_id_int)
        embed_novo = discord.Embed(title=p_info["titulo"], description=p_info["descricao"], color=discord.Color.blue())
        embed_novo.add_field(name="📦 Estoque", value=f"`{p_info['estoque']}` disponíveis", inline=True)
        embed_novo.add_field(name="💵 Valor Unitário", value=f"R$ `{p_info['preco']:.2f}`", inline=True)
        if p_info["foto"]: embed_novo.set_image(url=p_info["foto"])
        await msg.edit(embed=embed_novo, view=BotaoAbrirCarrinho())
        await interaction.response.send_message("✅ Painel editado com sucesso.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao editar discord: {e}", ephemeral=True)

@bot.tree.command(name="mandar_pix", description="Despacha os dados do PIX no carrinho.")
async def mandar_pix(interaction: discord.Interaction, chave: str = None):
    if not tem_permissao(interaction): return
    canal_id = interaction.channel.id
    if canal_id not in dados_carrinhos: return await interaction.response.send_message("❌ Use dentro do carrinho.", ephemeral=True)
        
    chave_usar = chave if chave else configs.get("chave_pix", "Não configurada")
    info = dados_carrinhos[canal_id]
    total = info["preco"] * info["qtd"]
    
    await interaction.response.send_message("✅ PIX enviado!", ephemeral=True)
    await interaction.channel.send(f"⚠️ **AVISO:** Pedido pronto.\n📦 **{info['produto_nome']}** - `{info['qtd']}x`\n💰 **R$ {total:.2f}**\n\n🔑 **PIX:** `{chave_usar}`")
    await enviar_log(interaction.guild, discord.Embed(title="💳 PIX Enviado", description=f"Em: {interaction.channel.mention}.", color=discord.Color.orange()))

@bot.tree.command(name="aprovar", description="Aprova compra do carrinho.")
async def aprovar(interaction: discord.Interaction, produto: str):
    if not tem_permissao(interaction): return
    canal_id = interaction.channel.id
    if canal_id not in dados_carrinhos: return await interaction.response.send_message("❌ Fora de carrinho.", ephemeral=True)

    info = dados_carrinhos[canal_id]
    cliente = await bot.fetch_user(info["cliente_id"])
    total_venda = info["preco"] * info["qtd"]

    # Salva Venda no Histórico (Memória + Firebase)
    venda_dados = {"valor": total_venda, "qtd": info["qtd"], "produto": info["produto_nome"], "data": datetime.now().isoformat()}
    historico_vendas.append(venda_dados)
    
    venda_id = f"venda_{int(datetime.now().timestamp())}_{info['cliente_id']}"
    asyncio.create_task(gravar_fb(f"vendas/{venda_id}", venda_dados))

    # Baixa o Estoque
    panel_id = info["panel_id"]
    if panel_id in paineis_produtos:
        paineis_produtos[panel_id]["estoque"] = max(0, paineis_produtos[panel_id]["estoque"] - info["qtd"])
        asyncio.create_task(gravar_fb(f"paineis/{panel_id}/estoque", paineis_produtos[panel_id]["estoque"]))
        
        try:
            canal_p = interaction.guild.get_channel(paineis_produtos[panel_id]["canal_id"])
            msg_p = await canal_p.fetch_message(panel_id)
            p_i = paineis_produtos[panel_id]
            em = discord.Embed(title=p_i["titulo"], description=p_i["descricao"], color=discord.Color.blue())
            em.add_field(name="📦 Estoque", value=f"`{p_i['estoque']}` disponíveis", inline=True)
            em.add_field(name="💵 Valor Unitário", value=f"R$ `{p_i['preco']:.2f}`", inline=True)
            if p_i["foto"]: em.set_image(url=p_i["foto"])
            await msg_p.edit(embed=em, view=BotaoAbrirCarrinho())
        except: pass

    carrinhos_aprovados.add(canal_id)
    await interaction.response.send_message("✅ Venda validada.", ephemeral=True)
    
    # MENSAGEM ALEGRE E ANIMADA NO CARRINHO
    await interaction.channel.send("🥳 **COMPRA APROVADA COM SUCESSO!** 🎉\nMuito obrigado por fortalecer! Seu produto já foi enviado na DM, vai lá conferir. Tamo junto! 🚀\n⏳ *O carrinho vai fechar sozinho em 5 minutinhos.*")

    await enviar_log(interaction.guild, discord.Embed(title="🎉 Compra Aprovada", description=f"**Canal:** {interaction.channel.name}\n**Cliente:** {cliente.mention}\n**Total:** R$ `{total_venda:.2f}`", color=discord.Color.green(), timestamp=datetime.now()))

    try: await cliente.send(f"🎁 **Sua compra foi aprovada!**\n📦 Aqui está seu produto:\n`{produto}`")
    except: await interaction.channel.send(f"⚠️ {cliente.mention} DM Fechada!")

    # EMBED NO CANAL DE APROVADAS EXATAMENTE COMO PEDIU
    if configs.get("canal_aprovadas"):
        c_aprovadas = interaction.guild.get_channel(int(configs["canal_aprovadas"]))
        if c_aprovadas:
            avatar = cliente.display_avatar.url if cliente.avatar else bot.user.display_avatar.url
            
            desc_apv = (
                f"👤 **Cliente:** {cliente.mention}\n\n"
                f"📦 **Produto:** `{info['produto_nome']}`\n\n"
                f"🔢 **Quantidade:** `{info['qtd']}x`\n\n"
                f"♻️ **VALOR PAGO** `{total_venda:.2f}$`\n\n"
                f"✨ *O produto foi entregue automaticamente com segurança via Mensagem Direta (DM)!*"
            )
            
            embed_apv = discord.Embed(title="🎉 COMPRA REALIZADA COM SUCESSO!", description=desc_apv, color=discord.Color.brand_green())
            embed_apv.set_thumbnail(url=avatar)
            await c_aprovadas.send(embed=embed_apv)

    async def fechar_carrinho():
        await asyncio.sleep(300)
        try: await interaction.channel.delete()
        except: pass
    asyncio.create_task(fechar_carrinho())

# ================= INTERFACES (BOTÕES E MODAIS) =================

class BotaoAbrirCarrinho(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Comprar", style=discord.ButtonStyle.green, custom_id="btn_abrir")
    async def btn_compra(self, interaction: discord.Interaction, button: discord.ui.Button):
        panel_id = interaction.message.id
        painel_info = paineis_produtos.get(panel_id)
        if painel_info and painel_info["estoque"] <= 0: return await interaction.response.send_message("❌ Sem estoque.", ephemeral=True)

        guild = interaction.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        for d in donos_permitidos:
            dm = guild.get_member(d)
            if dm: overwrites[dm] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        cc = await guild.create_text_channel(name=f"🛒-carrinho-{interaction.user.name}", category=interaction.channel.category, overwrites=overwrites)
        await interaction.response.send_message(f"✅ Carrinho: {cc.mention}", ephemeral=True)

        # LOG DE CARRINHO ABERTO
        embed_log = discord.Embed(title="🛒 Carrinho Aberto", description=f"O usuário {interaction.user.mention} abriu o carrinho {cc.mention}.", color=discord.Color.blue(), timestamp=datetime.now())
        await enviar_log(guild, embed_log)

        nome, preco = (painel_info["titulo"], painel_info["preco"]) if painel_info else ("Produto", 0.0)
        dados_carrinhos[cc.id] = {"cliente_id": interaction.user.id, "qtd": 1, "panel_id": panel_id, "produto_nome": nome, "preco": preco}

        await cc.send(f"{interaction.user.mention}")
        await cc.send(embed=discord.Embed(title="🛒 Carrinho", description=f"Produto: **{nome}**\nQtd: `1x`\nTotal: R$ `{preco:.2f}`", color=discord.Color.light_grey()), view=InterfaceCarrinho(interaction.user.id))
        carrinhos_ativos_alerta.add(cc.id)

class InterfaceCarrinho(discord.ui.View):
    def __init__(self, c_id):
        super().__init__(timeout=None)
        self.c_id = c_id

    @discord.ui.button(label="COMPRA", style=discord.ButtonStyle.green, custom_id="c_conf")
    async def btn_conf(self, interaction: discord.Interaction, button: discord.ui.Button):
        carrinhos_ativos_alerta.discard(interaction.channel.id)
        await interaction.response.send_message("⏳ Aguarde o suporte...")

    @discord.ui.button(label="CANCELA", style=discord.ButtonStyle.danger, custom_id="c_canc")
    async def btn_canc(self, interaction: discord.Interaction, button: discord.ui.Button):
        carrinhos_ativos_alerta.discard(interaction.channel.id)
        
        # LOG DE CARRINHO FECHADO/CANCELADO
        embed_log = discord.Embed(title="❌ Carrinho Cancelado", description=f"O carrinho **{interaction.channel.name}** foi fechado por {interaction.user.mention}.", color=discord.Color.red(), timestamp=datetime.now())
        await enviar_log(interaction.guild, embed_log)
        
        await interaction.response.send_message("❌ Fechando...")
        await asyncio.sleep(2)
        try: await interaction.channel.delete()
        except: pass

if __name__ == "__main__":
    manter_online()
    bot.run(TOKEN_BOT)

