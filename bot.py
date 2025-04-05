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
    # Certifique-se que 'gemini-2.0-flash' é um modelo válido e disponível para sua API Key
    # Modelos comuns são 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro'
    model = genai.GenerativeModel('gemini-1.5-flash-latest', safety_settings=safety_settings) # <<< VERIFIQUE O NOME DO MODELO CORRETO AQUI
    log.info("API Gemini configurada com sucesso com o modelo gemini-1.5-flash-latest.") # Usei gemini-1.5-flash como exemplo mais comum
except Exception as e:
    log.exception(f"Erro ao configurar a API Gemini: {e}")
    exit()

# --- Ponto Crítico: Intents ---
# Habilite a "Message Content Intent" no Discord Developer Portal!
intents = discord.Intents.default()
intents.messages = True         # Necessário para receber eventos de mensagem
intents.guilds = True           # Necessário para funcionar em servidores
intents.message_content = True  # NECESSÁRIO PARA LER O CONTEÚDO DAS MENSAGENS EM SERVIDORES

# Criar o cliente do Discord
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    """Evento chamado quando o bot está conectado e pronto."""
    log.info(f'Bot conectado como {client.user}')
    log.info(f'ID do Bot: {client.user.id}')
    log.info('------')
    # Define o status do bot (opcional)
    await client.change_presence(activity=discord.Game(name="Respondendo menções com Gemini"))

@client.event
async def on_message(message):
    """Evento chamado quando uma mensagem é recebida."""
    # 1. Ignorar mensagens do próprio bot
    if message.author == client.user:
        return

    # 2. Ignorar mensagens que não são DMs nem mencionam o bot
    # Verifica se a mensagem é uma DM OU se o bot foi mencionado
    is_dm = isinstance(message.channel, discord.DMChannel)
    mentioned = client.user.mentioned_in(message)

    if not is_dm and not mentioned:
        #log.debug(f"Mensagem ignorada (não é DM nem menção): '{message.content}'")
        return

    # 3. Obter o conteúdo da mensagem
    user_message = ""
    if mentioned:
        # Remove a menção do bot da mensagem para obter a pergunta real
        # Limpa espaços extras nas bordas
        user_message = message.content.replace(f'<@!{client.user.id}>', '', 1).replace(f'<@{client.user.id}>', '', 1).strip()
        log.info(f"Menção recebida de {message.author} no canal #{message.channel} (Servidor: {message.guild}): '{user_message}'")
    elif is_dm:
        user_message = message.content.strip()
        log.info(f"DM recebida de {message.author}: '{user_message}'")

    # 4. Verificar se há conteúdo após a menção (ou na DM)
    if not user_message:
        # Se não houver texto após a menção ou na DM (exceto a própria menção)
        await message.channel.send(f"Olá, {message.author.mention}! Precisa de ajuda? Faça sua pergunta mencionando-me ou aqui na DM.")
        return

    # 5. Processar com Gemini
    async with message.channel.typing():
        try:
            # Enviar a mensagem do usuário para a API Gemini
            log.info(f"Enviando para Gemini: '{user_message}'")
            # Use generate_content_async para não bloquear o bot (melhor prática)
            response = await model.generate_content_async(user_message)
            log.info("Resposta recebida da Gemini.")

            # Verificar se a resposta tem conteúdo
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
                safety_feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else 'N/A'
                log.warning(f"Gemini não retornou texto para '{user_message}'. Possível bloqueio. Feedback: {safety_feedback}")
                await message.channel.send("Não consegui gerar uma resposta. Tente reformular sua pergunta ou verifique se o conteúdo é apropriado.")

        except Exception as e:
            # Lidar com erros da API Gemini ou outros problemas
            log.exception(f"Erro ao processar mensagem ou chamar API Gemini para '{user_message}': {e}")
            await message.channel.send("Desculpe, ocorreu um erro ao tentar processar sua solicitação. Tente novamente mais tarde.")

# Iniciar o bot usando o token
try:
    log.info("Iniciando o bot...")
    client.run(DISCORD_TOKEN)
except discord.LoginFailure:
    log.error("Erro: Token do Discord inválido. Verifique seu arquivo .env")
except discord.PrivilegedIntentsRequired:
    log.error("Erro: Intents Privilegiadas (como Message Content) não habilitadas no Portal do Desenvolvedor!")
    log.error("Vá para https://discord.com/developers/applications, selecione seu bot, vá em 'Bot' e ative a 'Message Content Intent'.")
except Exception as e:
    log.exception(f"Erro crítico ao iniciar ou rodar o bot: {e}")
