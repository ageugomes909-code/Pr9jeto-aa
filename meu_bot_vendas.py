import os
import asyncio
import time
import random
from threading import Thread
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands

# ==============================================
# CONFIGURAÇÕES DE SEGURANÇA E PERMISSÃO
# ==============================================
DONO_ID = 1410272734012772524  # Seu ID Principal

# Lista dinâmica de usuários autorizados
usuarios_autorizados_enviar = set()

# ==============================================
# WEB SERVER PARA MANTER O RENDER ONLINE (24/7)
# ==============================================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Sistema de Transmissão Seguro Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def manter_online():
    t = Thread(target=run, daemon=True)
    t.start()

# ==============================================
# CONFIGURAÇÃO DO BOT DISCORD
# ==============================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = commands.Bot(command_prefix="!", intents=intents)

TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))

@client.event
async def on_ready():
    print(f"✅ Bot conectado com sucesso como {client.user} | ID: {client.user.id}")
    await client.change_presence(activity=discord.Game(name="Proteção Anti-Spam Ativa 🛡️"))
    try:
        synced = await client.tree.sync()
        print(f"🔄 {len(synced)} comandos slash sincronizados.")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

# ==============================================
# VIEW DE GERENCIAMENTO DE SERVIDORES
# ==============================================
class ServidoresView(discord.ui.View):
    def __init__(self, bot, guilds):
        super().__init__(timeout=120)
        self.bot = bot
        
        options = [
            discord.SelectOption(
                label=g.name[:90],
                value=str(g.id),
                description=f"ID: {g.id} | Membros: {g.member_count}"
            ) for g in guilds[:25]
        ]
        if options:
            self.add_item(ServidorSelect(options, bot))

class ServidorSelect(discord.ui.Select):
    def __init__(self, options, bot):
        super().__init__(placeholder="📌 Selecione um servidor...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != DONO_ID:
            await interaction.response.send_message("❌ Apenas o dono pode gerenciar.", ephemeral=True)
            return

        guild_id = int(self.values[0])
        guild = self.bot.get_guild(guild_id)

        if guild:
            nome_guild = guild.name
            await guild.leave()
            await interaction.response.send_message(f"✅ Bot saiu do servidor **{nome_guild}** (`{guild_id}`).", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Servidor não encontrado.", ephemeral=True)

# ==============================================
# SISTEMA DE TRANSMISSÃO E LOGS AVANÇADOS
# ==============================================
async def processar_envio_elegante(guild: discord.Guild, log_channel: discord.TextChannel, mensagem: str, operador: str):
    try:
        await guild.chunk()
        membros = [m for m in guild.members if not m.bot]
        total = len(membros)

        if total == 0:
            await log_channel.send("⚠️ Nenhum membro válido encontrado.")
            return

        def gerar_barra(atual, maximo, tamanho=12):
            if maximo == 0:
                return "[░░░░░░░░░░░░] 0%"
            pct = int((atual / maximo) * 100)
            preenchido = int((atual / maximo) * tamanho)
            barra = "█" * preenchido + "░" * (tamanho - preenchido)
            return f"[{barra}] {pct}%"

        # 1. LOG DE INÍCIO
        embed_inicio = discord.Embed(
            title="🛡️ Transmissão Segura Iniciada",
            description="Envio configurado com proteção dinâmica contra banimentos e logs em tempo real.",
            color=0x2B2D31
        )
        embed_inicio.add_field(name="🎯 Membros Alvo", value=f"`{total} pessoas`", inline=True)
        embed_inicio.add_field(name="👤 Operador", value=f"`{operador}`", inline=True)
        embed_inicio.add_field(name="⏱️ Proteção", value="`5s-9s por membro / Pausa a cada 5`", inline=False)
        embed_inicio.set_footer(text="Acompanhe o painel dinâmico abaixo.")
        embed_inicio.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed_inicio)

        # 2. PAINEL DE PROGRESSO
        embed_painel = discord.Embed(
            title="📊 Painel de Controle de Envio",
            color=0x5865F2
        )
        embed_painel.add_field(name="Status", value="🔄 `Enviando com segurança...`", inline=False)
        embed_painel.add_field(name="✅ Entregues", value="`0`", inline=True)
        embed_painel.add_field(name="❌ Falhas", value="`0`", inline=True)
        embed_painel.add_field(name="📈 Progresso", value=gerar_barra(0, total), inline=False)
        
        painel_msg = await log_channel.send(embed=embed_painel)

        sucessos = 0
        falhas = 0
        erros_consecutivos = 0
        inicio_tempo = time.time()

        for idx, membro in enumerate(membros, start=1):
            timestamp = discord.utils.utcnow().strftime("%H:%M:%S")

            # FREIO DE EMERGÊNCIA: Se a API negar 3 vezes seguidas, cancela o disparo para não tomar ban
            if erros_consecutivos >= 3:
                embed_alerta = discord.Embed(
                    title="🚨 FREIO DE EMERGÊNCIA DISPARADO",
                    description="O Discord retornou múltiplos erros consecutivos. O envio foi abortado automaticamente para salvar seu Bot!",
                    color=0xED4245
                )
                await log_channel.send(embed=embed_alerta)
                break

            try:
                await membro.send(mensagem)
                sucessos += 1
                erros_consecutivos = 0  # Reseta os erros após sucesso

                # LOG BONITO DE SUCESSO
                log_embed = discord.Embed(
                    title=f"✅ Entregue com Sucesso [{idx}/{total}]",
                    color=0x57F287
                )
                log_embed.add_field(name="👤 Destinatário", value=f"{membro.mention} (`{membro.id}`)", inline=False)
                log_embed.add_field(name="💬 Mensagem", value=f"```text\n{mensagem[:300]}\n```", inline=False)
                log_embed.add_field(name="🕒 Horário", value=f"`{timestamp}`", inline=True)
                
                if membro.display_avatar:
                    log_embed.set_thumbnail(url=membro.display_avatar.url)

                await log_channel.send(embed=log_embed)

            except discord.Forbidden:
                falhas += 1
                erros_consecutivos += 1
                err_embed = discord.Embed(title=f"❌ Falha de Permissão [{idx}/{total}]", color=0xED4245)
                err_embed.add_field(name="👤 Destinatário", value=f"{membro.mention} (`{membro.id}`)", inline=True)
                err_embed.add_field(name="⚠️ Motivo", value="`DM Fechada / Bloqueou o Bot`", inline=True)
                await log_channel.send(embed=err_embed)

            except discord.HTTPException as e:
                falhas += 1
                erros_consecutivos += 1
                err_embed = discord.Embed(title=f"⚠️ Limitação de API [{idx}/{total}]", color=0xFEE75C)
                err_embed.add_field(name="👤 Destinatário", value=f"{membro.mention}", inline=True)
                err_embed.add_field(name="⚠️ Detalhes", value=f"```text\n{e.text}\n```", inline=False)
                await log_channel.send(embed=err_embed)

            except Exception as e:
                falhas += 1
                erros_consecutivos += 1
                err_embed = discord.Embed(title=f"🚨 Erro Inesperado [{idx}/{total}]", color=0x95A5A6)
                err_embed.add_field(name="👤 Destinatário", value=f"{membro.mention}", inline=True)
                err_embed.add_field(name="⚠️ Detalhes", value=f"```text\n{e}\n```", inline=False)
                await log_channel.send(embed=err_embed)

            # Atualização do Painel a cada 2 envios
            if idx % 2 == 0 or idx == total:
                embed_painel.set_field_at(1, name="✅ Entregues", value=f"`{sucessos}`", inline=True)
                embed_painel.set_field_at(2, name="❌ Falhas", value=f"`{falhas}`", inline=True)
                embed_painel.set_field_at(3, name="📈 Progresso", value=gerar_barra(idx, total), inline=False)
                await painel_msg.edit(embed=embed_painel)

            # --- SISTEMA ANTI-BAN ---
            # 1. Delay humanizado entre 5.0 e 9.0 segundos por envio
            delay_aleatorio = random.uniform(5.0, 9.0)
            await asyncio.sleep(delay_aleatorio)

            # 2. Pausa estendida a cada 5 mensagens
            if idx % 5 == 0 and idx < total:
                pausa_msg = await log_channel.send(
                    embed=discord.Embed(
                        title="⏸️ Pausa de Segurança Anti-Spam",
                        description="Pausando por **15 segundos** para evitar que o algoritmo do Discord bloqueie a conta...",
                        color=0xFEE75C
                    )
                )
                await asyncio.sleep(15.0)
                try:
                    await pausa_msg.delete()
                except:
                    pass

        tempo_decorrido = round(time.time() - inicio_tempo, 2)

        # Atualiza Painel para Concluído
        embed_painel.color = 0x57F287
        embed_painel.set_field_at(0, name="Status", value="✅ **Transmissão Finalizada!**", inline=False)
        embed_painel.set_field_at(3, name="📈 Progresso", value=gerar_barra(total, total), inline=False)
        await painel_msg.edit(embed=embed_painel)

        # RELATÓRIO FINAL
        embed_fim = discord.Embed(
            title="🏁 Relatório da Transmissão",
            description="Processo concluído com proteções ativas.",
            color=0x57F287
        )
        embed_fim.add_field(name="✅ Sucessos", value=f"`{sucessos}`", inline=True)
        embed_fim.add_field(name="❌ Falhas", value=f"`{falhas}`", inline=True)
        embed_fim.add_field(name="📦 Total", value=f"`{total}`", inline=True)
        embed_fim.add_field(name="⏱️ Tempo Total", value=f"`{tempo_decorrido}s`", inline=False)
        embed_fim.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed_fim)

    except Exception as e:
        await log_channel.send(f"🚨 Erro crítico durante o processamento: `{e}`")

# ==============================================
# COMANDOS SLASH (/)
# ==============================================

@client.tree.command(name="enviar", description="Envia mensagem privada para os membros com proteção anti-ban")
@app_commands.describe(mensagem="Mensagem a ser enviada no PV", canal_logs="Canal de logs (Opcional)")
async def enviar(interaction: discord.Interaction, mensagem: str, canal_logs: discord.TextChannel = None):
    is_owner = interaction.user.id == DONO_ID
    is_authorized = interaction.user.id in usuarios_autorizados_enviar
    is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False

    if not (is_owner or is_authorized or is_admin):
        await interaction.response.send_message("❌ Você não possui permissão para usar este comando!", ephemeral=True)
        return

    target_channel = canal_logs or (interaction.guild.get_channel(LOG_CHANNEL_ID) if LOG_CHANNEL_ID != 0 else interaction.channel)

    await interaction.response.send_message(f"✅ **Envio iniciado de forma segura!** Logs em: {target_channel.mention}", ephemeral=True)

    asyncio.create_task(
        processar_envio_elegante(interaction.guild, target_channel, mensagem, str(interaction.user))
    )

@client.tree.command(name="reset", description="Reinicia a memória interna do bot e restaura a presença")
async def reset(interaction: discord.Interaction):
    if interaction.user.id != DONO_ID:
        await interaction.response.send_message("❌ Apenas o dono pode reiniciar o bot.", ephemeral=True)
        return

    usuarios_autorizados_enviar.clear()
    await client.change_presence(activity=discord.Game(name="Reiniciando... 🔄"), status=discord.Status.idle)
    await asyncio.sleep(2)
    await client.change_presence(activity=discord.Game(name="Proteção Anti-Spam Ativa 🛡️"), status=discord.Status.online)

    embed = discord.Embed(
        title="🔄 Bot Resetado",
        description="A memória do bot foi limpa com sucesso.",
        color=0x9B59B6
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="autorizar", description="Concede acesso ao comando /enviar")
async def autorizar(interaction: discord.Interaction, usuario: discord.User):
    if interaction.user.id != DONO_ID:
        await interaction.response.send_message("❌ Apenas o dono pode autorizar.", ephemeral=True)
        return
    usuarios_autorizados_enviar.add(usuario.id)
    await interaction.response.send_message(f"✅ {usuario.mention} foi autorizado.", ephemeral=True)

@client.tree.command(name="remover", description="Revoga o acesso de um usuário")
async def remover(interaction: discord.Interaction, usuario: discord.User):
    if interaction.user.id != DONO_ID:
        await interaction.response.send_message("❌ Apenas o dono pode revogar acessos.", ephemeral=True)
        return
    if usuario.id in usuarios_autorizados_enviar:
        usuarios_autorizados_enviar.remove(usuario.id)
        await interaction.response.send_message(f"⚠️ {usuario.mention} foi removido dos autorizados.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Usuário não estava na lista.", ephemeral=True)

@client.tree.command(name="servidores", description="Lista os servidores em que o bot está instalado")
async def servidores(interaction: discord.Interaction):
    if interaction.user.id != DONO_ID:
        await interaction.response.send_message("❌ Apenas o dono pode visualizar.", ephemeral=True)
        return
    guilds = client.guilds
    if not guilds:
        await interaction.response.send_message("Nenhum servidor conectado.", ephemeral=True)
        return

    embed = discord.Embed(title="🌐 Servidores Conectados", color=0x3498DB)
    for g in guilds[:10]:
        embed.add_field(name=f"📌 {g.name}", value=f"🆔 `{g.id}` | 👥 `{g.member_count} membros`", inline=False)

    view = ServidoresView(client, guilds)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==============================================
# INICIALIZAÇÃO
# ==============================================
if __name__ == "__main__":
    manter_online()
    if TOKEN:
        client.run(TOKEN)
    else:
        print("🚨 ERRO: Configure a variável DISCORD_TOKEN no painel do Render!")

