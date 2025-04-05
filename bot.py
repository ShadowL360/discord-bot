import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging # Adicionado para melhor logging

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__)

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Verificar se as chaves foram carregadas
if not DISCORD_TOKEN:
    log.error("Erro: Token do Discord não encontrado. Verifique seu arquivo .env")
    exit()
if not GEMINI_API_KEY:
    log.error("Erro: Chave da API Gemini não encontrada. Verifique seu arquivo .env")
    exit()

# Configurar a API Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Configurações de segurança opcionais (ajuste conforme necessário)
    # Veja mais em: https://ai.google.dev/docs/safety_setting_gemini
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
    # Modelo Flash mais recente disponível publicamente (em meados de 2024).
    # Verifique a documentação oficial do Google AI para os nomes de modelo mais atuais disponíveis para sua API Key.
    # 'gemini-2.0-flash' não é um nome de modelo público padrão no momento.
    MODEL_NAME = 'gemini-1.5-flash-latest'
    model = genai.GenerativeModel(MODEL_NAME, safety_settings=safety_settings)
    log.info(f"API Gemini configurada com sucesso com o modelo '{MODEL_NAME}'.")
except Exception as e:
    log.exception(f"Erro ao configurar a API Gemini: {e}")
    exit()

# --- Ponto Crítico: Intents ---
# Habilite a "Message Content Intent" no Discord Developer Portal!
# Vá para https://discord.com/developers/applications -> Seu App -> Bot -> Privileged Gateway Intents
intents = discord.Intents.default()
intents.messages = True         # Necessário para receber eventos de mensagem (on_message)
intents.guilds = True           # Necessário para identificar servidores, canais, etc.
intents.message_content = True  # NECESSÁRIO PARA LER O CONTEÚDO DAS MENSAGENS EM SERVIDORES (Requer verificação do bot >100 servidores)

# Criar o cliente do Discord (funciona com discord.py v2.0+)
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    """Evento chamado quando o bot está conectado e pronto."""
    log.info(f'Bot conectado como {client.user}')
    log.info(f'ID do Bot: {client.user.id}')
    # Define o status do bot (opcional)
    await client.change_presence(activity=discord.Game(name="Respondendo menções com Gemini 1.5 Flash"))
    log.info('------ Bot Pronto ------')


@client.event
async def on_message(message: discord.Message): # Adicionado type hint para clareza
    """Evento chamado quando uma mensagem é recebida."""
    # 1. Ignorar mensagens do próprio bot
    if message.author == client.user:
        return

    # 2. Determinar se o bot deve responder
    is_dm = isinstance(message.channel, discord.DMChannel)
    mentioned = client.user.mentioned_in(message)

    # Ignorar se não for DM e não for menção direta
    if not is_dm and not mentioned:
        # log.debug(f"Mensagem ignorada (não é DM nem menção): '{message.content}'") # Descomente para debug detalhado
        return

    # 3. Obter o conteúdo da mensagem limpo
    user_message = ""
    if mentioned:
        # Remove a menção do bot (tanto <@!ID> quanto <@ID>) e espaços extras
        clean_content = message.content.replace(f'<@!{client.user.id}>', '', 1).replace(f'<@{client.user.id}>', '', 1).strip()
        user_message = clean_content
        log.info(f"Menção recebida de {message.author} ({message.author.id}) no canal #{message.channel} (Servidor: {message.guild}): '{user_message}'")
    elif is_dm:
        user_message = message.content.strip()
        log.info(f"DM recebida de {message.author} ({message.author.id}): '{user_message}'")

    # 4. Verificar se há conteúdo após a limpeza
    if not user_message:
        log.info(f"Recebida menção/DM vazia de {message.author}. Enviando mensagem de ajuda.")
        try:
            # Enviar uma mensagem de ajuda se não houver prompt
            await message.channel.send(f"Olá, {message.author.mention}! Precisa de ajuda? Faça sua pergunta mencionando-me ou aqui na DM.")
        except discord.errors.Forbidden:
            log.warning(f"Não foi possível enviar mensagem de ajuda para {message.author} no canal {message.channel} (permissões?).")
        except Exception as e:
            log.exception(f"Erro ao enviar mensagem de ajuda para {message.author}: {e}")
        return

    # 5. Processar com Gemini
    async with message.channel.typing(): # Mostra "Bot está digitando..."
        try:
            # Enviar a mensagem do usuário para a API Gemini de forma assíncrona
            log.info(f"Enviando para Gemini: '{user_message}'")
            response = await model.generate_content_async(user_message)
            log.info("Resposta recebida da Gemini.")

            # Verificar se a resposta tem conteúdo de texto
            if response.text:
                gemini_reply = response.text
                # Enviar a resposta da Gemini de volta para o Discord
                # Dividir a mensagem se for maior que 2000 caracteres
                for i in range(0, len(gemini_reply), 2000):
                    chunk = gemini_reply[i:i+2000]
                    await message.channel.send(chunk)
                    log.info(f"Enviado chunk de resposta para {message.author}.")

            else:
                # Se a API não retornar texto (pode ser bloqueado por segurança, etc.)
                try:
                    # Tenta acessar o feedback de segurança, se existir
                    safety_feedback = response.prompt_feedback
                    block_reason = safety_feedback.block_reason if hasattr(safety_feedback, 'block_reason') else 'N/A'
                    log.warning(f"Gemini não retornou texto para '{user_message}'. Possível bloqueio por segurança. Razão: {block_reason}. Feedback completo: {safety_feedback}")
                    await message.channel.send(f"Não consegui gerar uma resposta para sua mensagem. Pode ter sido bloqueada por segurança (Razão: {block_reason}). Tente reformular.")
                except (ValueError, AttributeError):
                     # Caso 'response.text' seja None mas não haja 'prompt_feedback' claro ou dê erro ao acessar
                    log.warning(f"Gemini não retornou texto para '{user_message}', e não foi possível obter feedback de segurança claro. Resposta bruta: {response}")
                    await message.channel.send("Não consegui gerar uma resposta. Tente reformular sua pergunta ou verifique se o conteúdo é apropriado.")


        except Exception as e:
            # Lidar com erros da API Gemini ou outros problemas inesperados
            log.exception(f"Erro ao processar mensagem ou chamar API Gemini para '{user_message}': {e}")
            try:
                await message.channel.send("Desculpe, ocorreu um erro ao tentar processar sua solicitação. A equipe foi notificada (ou deveria!). Tente novamente mais tarde.")
            except discord.errors.Forbidden:
                 log.error(f"Não foi possível enviar mensagem de erro para {message.author} no canal {message.channel} (permissões?).")
            except Exception as inner_e:
                 log.exception(f"Erro adicional ao tentar enviar mensagem de erro ao usuário: {inner_e}")

# Iniciar o bot usando o token
try:
    log.info("Iniciando o bot...")
    client.run(DISCORD_TOKEN)
except discord.LoginFailure:
    log.error("--- ERRO CRÍTICO: TOKEN DO DISCORD INVÁLIDO ---")
    log.error("Verifique o DISCORD_TOKEN no seu arquivo .env ou variável de ambiente.")
except discord.PrivilegedIntentsRequired:
    log.error("--- ERRO CRÍTICO: INTENTS PRIVILEGIADAS NÃO HABILITADAS ---")
    log.error("A 'Message Content Intent' é necessária para ler mensagens.")
    log.error("Vá para https://discord.com/developers/applications -> Seu App -> Bot -> Ative 'Message Content Intent'.")
except Exception as e:
    log.exception(f"Erro crítico não tratado ao iniciar ou rodar o bot: {e}")
