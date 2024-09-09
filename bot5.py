import os
import requests
import json
from urllib import request as url_request
from dotenv import load_dotenv
import interactions
import websockets
import uuid
import urllib.parse
import time
from io import BytesIO
from PIL import Image
import aiohttp
import logging 
import base64

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
server_address = "192.168.8.219:8188"
client_id = str(uuid.uuid4())

bot = interactions.Client(token=DISCORD_TOKEN)

def initialize_ollama():
    url = 'http://192.168.8.220:11434/api/generate'
    data = {
        'model': 'gemma2:27b'
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        print('Ollama initialization successful.')
    except requests.exceptions.RequestException as e:
        print(f'Error initializing Ollama API: {e}')

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.me}')
    initialize_ollama()

@interactions.slash_command(
    name="gem",
    description="Send a message to the Ollama API",
    options=[
        interactions.SlashCommandOption(
            name="query",
            description="The query to send to the Ollama API",
            type=interactions.OptionType.STRING,
            required=True,
        )
    ]
)
async def gem(ctx: interactions.ComponentContext, query: str):
    await ctx.defer()  # Acknowledge the command to avoid timeout
    response = get_ollama_response(query)
    await ctx.send(response)

@interactions.slash_command(
    name="img",
    description="Load the prompt for flux image generation",
    options=[
        interactions.SlashCommandOption(
            name="text",
            description="The text prompt for the image generation",
            type=interactions.OptionType.STRING,
            required=True,
        ),
        interactions.SlashCommandOption(
            name="width",
            description="The width of the image",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
        interactions.SlashCommandOption(
            name="height",
            description="The height of the image",
            type=interactions.OptionType.INTEGER,
            required=False,
        ),
    ]
)
async def img(ctx: interactions.ComponentContext, text: str, width: int = 1024, height: int = 1024):
    await ctx.defer()  # Acknowledge the command to avoid timeout
    try:
        prompt = load_prompt("flux-api.json")
        prompt["6"]["inputs"]["text"] = text
        if width is not None and height is not None:
            prompt["27"]["inputs"]["width"] = width
            prompt["27"]["inputs"]["height"] = height
        else:
            prompt["27"]["inputs"]["width"] = 1024
            prompt["27"]["inputs"]["height"] = 1024
        # Connect to the WebSocket
        # ws = websocket.WebSocket()
        # try:
        #     ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
        #     ws.send(json.dumps(prompt))

        #     # Receive the image data
        #     images = get_images(ws, prompt)
        # finally:
        #     ws.close()  # Ensure the WebSocket is closed after use
        
        uri = f"ws://{server_address}/ws?clientId={client_id}"

        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps(prompt))

            # Receive the image data
            images = await get_images(ws, prompt)
            for node_id in images:
                for image_data in images[node_id]:
                    # Open image from binary data
                    image = Image.open(BytesIO(image_data))

                    # Save image to a BytesIO buffer
                    with BytesIO() as image_binary:
                        image.save(image_binary, 'PNG')
                        image_binary.seek(0)

                        # Send the image in Discord
        #                await message.channel.send(file=discord.File(fp=image_binary, filename=f'{node_id}.png'))
                        await ctx.send(files=[interactions.File(image_binary, file_name=f'{node_id}.png')])
    except ConnectionResetError as e:
        logger.error(f"Connection reset error: {e}")
        await ctx.send("An error occurred while processing your request. Please try again later.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await ctx.send("An unexpected error occurred. Please try again later.")
#    print(images)
#    for image_data in images:
#        await ctx.send(files=interactions.File(fp=image_data, filename="image.png"))

@interactions.slash_command(
    name="i2i",
    description="Invoke flux image2image prompt",
    options=[
        interactions.SlashCommandOption(
            name="text",
            description="The text prompt for the image2image generation",
            type=interactions.OptionType.STRING,
            required=True,
        ),
        interactions.SlashCommandOption(
            name="image",
            description="The image to be used for image2image generation",
            type=interactions.OptionType.ATTACHMENT,
            required=True,
        ),
        interactions.SlashCommandOption(
            name="denoise",
            description="Controls how similar the output is to the original (smaller values are more similar)",
            type=interactions.OptionType.NUMBER,
            required=False,
        ),        
    ]
)
async def i2i(ctx: interactions.ComponentContext, text: str, image: interactions.Attachment, denoise: float = 0.7):
    await ctx.defer()  # Acknowledge the command to avoid timeout

    try:
        # Download the image using aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(image.url) as response:
                image_data = await response.read()
                image = Image.open(BytesIO(image_data))
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        width_org = int(image.width) 
        height_org = int(image.height) 
        aspect = width_org / height_org
        if ((width_org * height_org) > 3686400):            
            if aspect > 1:
                width = 1920
                height = int(1920 / aspect)
            else:
                width = int(1920 * aspect)
                height = 1920
        else:
            width = width_org
            height = height_org
        image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        # Load the workflow file
        #prompt = json.load(open('i2iflux-base64.json'))
        prompt = load_prompt("i2iflux-base64.json")

        # Assign the text and image to the appropriate nodes
        prompt["6"]["inputs"]["text"] = text
        prompt["53"]["inputs"]["image"] = image_base64
        prompt["51"]["inputs"]["width"] = width
        prompt["51"]["inputs"]["height"] = height
        prompt["17"]["inputs"]["denoise"] = denoise
        # Connect to the WebSocket
        # ws = websocket.WebSocket()
        # try:
        #     ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
        #     ws.send(json.dumps(prompt))

        #     # Receive the image data
        #     images = get_images(ws, prompt)
        # finally:
        #     ws.close()  # Ensure the WebSocket is closed after use

        uri = f"ws://{server_address}/ws?clientId={client_id}"

        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps(prompt))

            # Receive the image data
            images = await get_images(ws, prompt)
            for node_id in images:
                for image_data in images[node_id]:
                    # Open image from binary data
                    image = Image.open(BytesIO(image_data))

                    # Save image to a BytesIO buffer
                    with BytesIO() as image_binary:
                        image.save(image_binary, 'PNG')
                        image_binary.seek(0)

                        # Send the image in Discord
        #                await message.channel.send(file=discord.File(fp=image_binary, filename=f'{node_id}.png'))
                        await ctx.send(files=[interactions.File(image_binary, file_name=f'{node_id}.png')])

    except aiohttp.ClientResponseError as e:
        logger.error(f"Client response error: {e.status} {e.message}")
        await ctx.send("An error occurred while processing your request. Please try again later.")
    except ConnectionResetError as e:
        logger.error(f"Connection reset error: {e}")
        await ctx.send("An error occurred while processing your request. Please try again later.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await ctx.send("An unexpected error occurred. Please try again later.")

@interactions.slash_command(
    name="des",
    description="generate a description for an image",
    options=[
        interactions.SlashCommandOption(
            name="image",
            description="The image to be used for image2image generation",
            type=interactions.OptionType.ATTACHMENT,
            required=True,
        ),
    ]
)
async def des(ctx: interactions.ComponentContext, image: interactions.Attachment):
    await ctx.defer()  # Acknowledge the command to avoid timeout
    try:
        # Download the image using aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(image.url) as response:
                image_data = await response.read()
                image = Image.open(BytesIO(image_data))
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        prompt = load_prompt("florance_api.json")
        uri = f"ws://{server_address}/ws?clientId={client_id}"

        prompt["62"]["inputs"]["image"] = image_base64
        # Log the prompt being sent
        logger.info(f"Sending prompt to server: {json.dumps(prompt)}")

        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps(prompt))
            # Wait for the server to process the prompt and send the output
            response = await ws.recv()
            logger.info(f"Received response from server: {response}")
            response_data = json.loads(response)
            if isinstance(response_data, dict):
                response_data = json.dumps(response_data)
            await ctx.send(response_data)
    except ConnectionResetError as e:
        logger.error(f"Connection reset error: {e}")
        await ctx.send("An error occurred while processing your request. Please try again later.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await ctx.send("An unexpected error occurred. Please try again later.")

def get_ollama_response(query):
    url = 'http://192.168.8.220:11434/api/chat'
    data = {
        'model': 'gemma2:27b',
        'messages': [
            {
                'role': 'user',
                'content': query
            }
        ],
        'stream': False
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json().get('message', {}).get('content', 'Sorry, I could not process your request.')
    except requests.exceptions.RequestException as e:
        print(f'Error querying Ollama API: {e}')
        return 'Sorry, I could not process your request.'

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req =  urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()

def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())

async def get_images(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_images = {}
    while True:
        out = await ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break #Execution is done
        else:
            continue #previews are binary data

    history = get_history(prompt_id)[prompt_id]
    for o in history['outputs']:
        for node_id in history['outputs']:
            node_output = history['outputs'][node_id]
            if 'images' in node_output:
                images_output = []
                for image in node_output['images']:
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    images_output.append(image_data)
            output_images[node_id] = images_output

    return output_images

def load_prompt(filename):
    with open(filename, 'r') as file:
        return json.load(file)

async def process_images(server_address, client_id, prompt):
    uri = f"ws://{server_address}/ws?clientId={client_id}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(prompt))

        # Receive the image data
        images = await get_images(ws, prompt)
        return images

bot.start()