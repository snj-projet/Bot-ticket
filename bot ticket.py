import discord
from discord.ext import commands
from discord.ui import Button, View, Select, Modal
import datetime
import os
import aiofiles
import io
import re
import asyncio
import json

TOKEN = "TOKEN BOT"
GUILD_ID = 

DEFAULT_CATEGORY_ID = 

LOG_CHANNEL_ID = 

STAFF_ROLE_ID = 

TRANSCRIPTS_FOLDER = "transcripts"

TICKET_CATEGORIES_FILE = "ticket_categories.json"

DEFAULT_TICKET_CATEGORIES = [
    "Gestion Staff",
    "Gestion Abus",
    "Ticket Owner"
]

CATEGORY_IDS = {}

TICKET_CATEGORIES = []

def has_staff_role(ctx):
    if ctx.author.guild_permissions.administrator:
        return True
    
    staff_role = discord.utils.get(ctx.guild.roles, id=STAFF_ROLE_ID)
    if staff_role is None:
        return ctx.author.guild_permissions.manage_channels or ctx.author.guild_permissions.manage_guild
    
    return staff_role in ctx.author.roles

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True  

client = commands.Bot(command_prefix="!", intents=intents)

class TicketSetupView(View):
    def __init__(self):
        super().__init__()
        self.add_item(EditTicketSettingsButton())

class EditTicketSettingsButton(Button):
    def __init__(self):
        super().__init__(label="Configurer le Ticket", style=discord.ButtonStyle.primary)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketSettingsModal())

class TicketSettingsModal(Modal, title="Paramètres du Ticket"):
    title_input = discord.ui.TextInput(label="Titre du Ticket", placeholder="Ex: Support", required=True)
    description_input = discord.ui.TextInput(label="Description du Ticket", style=discord.TextStyle.paragraph, placeholder="Décrivez l'objectif du ticket", required=True)
    color_input = discord.ui.TextInput(label="Couleur de l'embed (hex)", placeholder="#3498db", required=True)
    categories_input = discord.ui.TextInput(label="Catégories (séparées par des virgules)", placeholder="Gestion Staff, Gestion Abus, Ticket Owner", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            color = discord.Color(int(self.color_input.value.strip("#"), 16))
        except ValueError:
            await interaction.response.send_message("❌ Couleur invalide. Utilisez un code hexadécimal comme #3498db.", ephemeral=True)
            return
        
        custom_categories = [cat.strip() for cat in self.categories_input.value.split(",") if cat.strip()]
        
        if not custom_categories:
            await interaction.response.send_message("⚠️ Veuillez spécifier au moins une catégorie de ticket.", ephemeral=True)
            return
        
        global TICKET_CATEGORIES
        TICKET_CATEGORIES = custom_categories
        
        save_ticket_categories()
        
        embed = discord.Embed(
            title=self.title_input.value, 
            description=self.description_input.value, 
            color=color,
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(
            name="📃 Comment ouvrir un ticket",
            value="1. Sélectionnez une catégorie dans le menu déroulant ci-dessous\n2. Cliquez sur le bouton 'Ouvrir un Ticket'\n3. Un nouveau canal sera créé pour votre demande",
            inline=False
        )
        
        categories_text = ""
        for category in custom_categories:
            emoji = "📝" 
            if "staff" in category.lower():
                emoji = "👤" 
            elif "abus" in category.lower():
                emoji = "⚠️" 
            elif "owner" in category.lower() or "propriétaire" in category.lower():
                emoji = "👑"  
            elif "partenariat" in category.lower() or "partner" in category.lower():
                emoji = "🤝"
            elif "bug" in category.lower():
                emoji = "🐛"  
            elif "suggestion" in category.lower():
                emoji = "💡"  
            categories_text += f"{emoji} **{category}**\n"
        
        embed.add_field(
            name="📁 Catégories disponibles",
            value=categories_text,
            inline=False
        )
        
        embed.set_footer(text=f"Système de tickets configuré par {interaction.user.name}")
        
        guild = interaction.guild
        for category_name in custom_categories:
            existing_category = discord.utils.get(guild.categories, name=category_name)
            
            if existing_category:
                CATEGORY_IDS[category_name] = existing_category.id
            else:
                try:
                    staff_role = discord.utils.get(guild.roles, id=STAFF_ROLE_ID)
                    
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    }
                    
                    if staff_role:
                        overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
                    
                    new_category = await guild.create_category(name=category_name, overwrites=overwrites)
                    CATEGORY_IDS[category_name] = new_category.id
                except Exception as e:
                    print(f"[ERROR] Failed to create category '{category_name}': {e}")
        
        await interaction.response.send_message("✅ Configuration enregistrée ! Les catégories ont été mises à jour.", ephemeral=True)
        await interaction.channel.send(embed=embed, view=CategorySelectionView(custom_categories))

class CategorySelectionView(View):
    def __init__(self, categories):
        super().__init__()
        self.add_item(CategorySelect(categories))

class CategorySelect(Select):
    def __init__(self, categories):
        options = []
        for cat in categories:
            description = f"Créer un ticket pour {cat}"
            
            emoji = "📝"  
            if "staff" in cat.lower():
                emoji = "👤"
            elif "abus" in cat.lower():
                emoji = "⚠️" 
            elif "owner" in cat.lower() or "propriétaire" in cat.lower():
                emoji = "👑" 
            elif "partenariat" in cat.lower() or "partner" in cat.lower():
                emoji = "🤝"  
            elif "bug" in cat.lower():
                emoji = "🐛" 
            elif "suggestion" in cat.lower():
                emoji = "💡"  
            
            options.append(discord.SelectOption(
                label=cat,
                description=description,
                value=cat,
                emoji=emoji
            ))
             
        super().__init__(placeholder="Choisissez une catégorie de ticket", options=options, min_values=1, max_values=1)
    
    async def callback(self, interaction: discord.Interaction):
        category_choice = self.values[0]
        await interaction.response.send_message("Cliquez sur le bouton ci-dessous pour ouvrir un ticket.", view=OpenTicketView(category_choice), ephemeral=True)

class OpenTicketView(View):
    def __init__(self, category_choice):
        super().__init__()
        self.add_item(OpenTicketButton(category_choice))

class OpenTicketButton(Button):
    def __init__(self, category_choice):
        label = "Ouvrir un Ticket"
        style = discord.ButtonStyle.green
        emoji = "📩" 
        
        if "staff" in category_choice.lower():
            emoji = "👤"  
        elif "abus" in category_choice.lower():
            emoji = "⚠️" 
            style = discord.ButtonStyle.danger
        elif "owner" in category_choice.lower() or "propriétaire" in category_choice.lower():
            emoji = "👑"  
            style = discord.ButtonStyle.primary
        
        super().__init__(label=label, style=style, emoji=emoji)
        self.category_choice = category_choice
    
    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        staff_role = discord.utils.get(guild.roles, id=STAFF_ROLE_ID)

        await interaction.response.defer(ephemeral=True)
        
        if self.category_choice in CATEGORY_IDS:
            category_id = CATEGORY_IDS[self.category_choice]
            category = discord.utils.get(guild.categories, id=category_id)
        else:
            category = discord.utils.get(guild.categories, name=self.category_choice)
            
        if category is None:
            category = discord.utils.get(guild.categories, id=DEFAULT_CATEGORY_ID)
            if category is None:
                await interaction.followup.send(f"⚠️ Erreur : Impossible de trouver une catégorie pour les tickets '{self.category_choice}'.", ephemeral=True)
                return
            
            await interaction.followup.send(f"\u26a0\ufe0f Attention : Catégorie '{self.category_choice}' non trouvée, utilisation de la catégorie par défaut.", ephemeral=True)
        
        if staff_role is None:
            print(f"[WARNING] Staff role with ID {STAFF_ROLE_ID} not found. Using default permissions.")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        else:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
            }
        
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}-{self.category_choice}", 
            category=category, 
            overwrites=overwrites
        )
        
        await ticket_channel.send(
            f"{interaction.user.mention}, votre ticket pour **{self.category_choice}** a été ouvert !\n"
            f"Le staff vous répondra dès que possible.", 
            view=CloseTicketView()
        )
        
        await interaction.followup.send(f"🎟️ Ticket créé dans la catégorie **{self.category_choice}** : {ticket_channel.mention}", ephemeral=True)
        
        log_channel = discord.utils.get(guild.text_channels, id=LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title="🎟️ Ticket Ouvert", description=f"Ticket créé par {interaction.user.mention} ({interaction.user.name}) pour {self.category_choice}", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
            await log_channel.send(embed=embed)

class CloseTicketView(View):
    def __init__(self):
        super().__init__()
        self.add_item(CloseTicketButton())

class CloseTicketButton(Button):
    def __init__(self):
        super().__init__(label="Fermer le Ticket", style=discord.ButtonStyle.red)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel
        guild = interaction.guild
        
        await interaction.followup.send("Génération de la transcription et fermeture du ticket en cours...", ephemeral=True)
        
        try:
            transcript_file = await save_transcript(channel)
            
            with open(transcript_file, 'rb') as file:
                transcript_discord_file = discord.File(file, filename=os.path.basename(transcript_file))
                
                log_channel = discord.utils.get(guild.text_channels, id=LOG_CHANNEL_ID)
                if log_channel:
                    embed = discord.Embed(
                        title="🚪 Ticket Fermé", 
                        description=f"Ticket fermé par {interaction.user.mention} ({interaction.user.name}) dans {channel.name}", 
                        color=discord.Color.red(), 
                        timestamp=datetime.datetime.utcnow()
                    )
                    embed.add_field(name="Transcription", value="Voir le fichier HTML ci-joint pour la conversation complète", inline=False)
                    
                    await log_channel.send(embed=embed, file=transcript_discord_file)
                    
                    await channel.send("Ce ticket va être fermé. Une transcription a été sauvegardée.")
        except Exception as e:
            print(f"[ERROR] Failed to create transcript: {e}")
            if log_channel:
                embed = discord.Embed(title="🚪 Ticket Fermé", description=f"Ticket fermé par {interaction.user.mention} ({interaction.user.name}) dans {channel.name}", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
                await log_channel.send(embed=embed)
        
        await asyncio.sleep(3)
        
        await channel.delete()

async def save_transcript(channel):
    if not os.path.exists(TRANSCRIPTS_FOLDER):
        os.makedirs(TRANSCRIPTS_FOLDER)
    
    safe_channel_name = re.sub(r'[^\w\-_]', '_', channel.name)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{TRANSCRIPTS_FOLDER}/{safe_channel_name}_{timestamp}.html"
    
    messages = []
    async for message in channel.history(limit=500, oldest_first=True):
        messages.append(message)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ticket: {channel.name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #5865F2; color: white; padding: 10px; border-radius: 5px; margin-bottom: 20px; }}
            .message {{ margin-bottom: 15px; padding: 10px; border-radius: 5px; }}
            .message:nth-child(odd) {{ background-color: #f5f5f5; }}
            .author {{ font-weight: bold; margin-bottom: 5px; }}
            .timestamp {{ color: #666; font-size: 0.8em; margin-bottom: 5px; }}
            .content {{ margin-left: 10px; }}
            .footer {{ margin-top: 30px; text-align: center; font-size: 0.8em; color: #666; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Transcript du ticket: {channel.name}</h1>
            <p>Créé le: {channel.created_at.strftime('%d/%m/%Y à %H:%M:%S')}</p>
        </div>
        <div class="messages">
    """
    
    for message in messages:
        timestamp = message.created_at.strftime("%d/%m/%Y à %H:%M:%S")
        content = message.content.replace("<", "&lt;").replace(">", "&gt;")
        
        attachments = ""
        if message.attachments:
            attachments = "<br>".join([f"<a href='{a.url}' target='_blank'>{a.filename}</a>" for a in message.attachments])
        
        embeds = ""
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    embeds += f"<div style='border-left: 4px solid #5865F2; padding-left: 10px;'>"
                    embeds += f"<strong>{embed.title}</strong><br>"
                    if embed.description:
                        embeds += f"{embed.description.replace('<', '&lt;').replace('>', '&gt;')}<br>"
                    embeds += "</div>"
        
        html += f"""
        <div class="message">
            <div class="author">{message.author.name}#{message.author.discriminator}</div>
            <div class="timestamp">{timestamp}</div>
            <div class="content">{content}</div>
            {f'<div class="attachments">{attachments}</div>' if attachments else ''}
            {f'<div class="embeds">{embeds}</div>' if embeds else ''}
        </div>
        """
    
    html += """
        </div>
        <div class="footer">
            <p>Transcript généré le {datetime.datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</p>
        </div>
    </body>
    </html>
    """
    
    async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
        await f.write(html)
    
    return filename

def load_ticket_categories():
    global TICKET_CATEGORIES
    try:
        if os.path.exists(TICKET_CATEGORIES_FILE):
            with open(TICKET_CATEGORIES_FILE, 'r', encoding='utf-8') as f:
                TICKET_CATEGORIES = json.load(f)
                print(f"[INFO] Loaded {len(TICKET_CATEGORIES)} ticket categories from {TICKET_CATEGORIES_FILE}")
        else:
            TICKET_CATEGORIES = DEFAULT_TICKET_CATEGORIES.copy()
            save_ticket_categories()  
            print(f"[INFO] Created default ticket categories file: {TICKET_CATEGORIES_FILE}")
    except Exception as e:
        print(f"[ERROR] Failed to load ticket categories: {e}")
        TICKET_CATEGORIES = DEFAULT_TICKET_CATEGORIES.copy()

def save_ticket_categories():
    try:
        with open(TICKET_CATEGORIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(TICKET_CATEGORIES, f, indent=4)
        print(f"[INFO] Saved {len(TICKET_CATEGORIES)} ticket categories to {TICKET_CATEGORIES_FILE}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save ticket categories: {e}")
        return False

@client.event
async def on_ready():
    print(f"[OK] Connected as {client.user}")
    print(f"[INFO] Available on {len(client.guilds)} servers")
    
    load_ticket_categories()
    
    if not os.path.exists(TRANSCRIPTS_FOLDER):
        os.makedirs(TRANSCRIPTS_FOLDER)
        print(f"[INFO] Created transcripts folder: {TRANSCRIPTS_FOLDER}")
    else:
        print(f"[INFO] Using existing transcripts folder: {TRANSCRIPTS_FOLDER}")
    
    for guild in client.guilds:
        print(f"[INFO] Setting up ticket categories for: {guild.name} (ID: {guild.id})")
        
        for category_name in TICKET_CATEGORIES:
            existing_category = discord.utils.get(guild.categories, name=category_name)
            
            if existing_category:
                print(f"[INFO] Category '{category_name}' already exists with ID: {existing_category.id}")
                CATEGORY_IDS[category_name] = existing_category.id
            else:
                try:
                    staff_role = discord.utils.get(guild.roles, id=STAFF_ROLE_ID)
                    
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    }
                    
                    if staff_role:
                        overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
                    
                    new_category = await guild.create_category(name=category_name, overwrites=overwrites)
                    print(f"[INFO] Created category '{category_name}' with ID: {new_category.id}")
                    CATEGORY_IDS[category_name] = new_category.id
                except Exception as e:
                    print(f"[ERROR] Failed to create category '{category_name}': {e}")
        
        print(f"[INFO] Ticket categories setup complete for {guild.name}")
        print(f"[INFO] Category IDs: {CATEGORY_IDS}")
    
    print("[OK] Bot is ready to use!")
    print("[INFO] Use !setup to configure the ticket system")
    print("[INFO] Use !aide to see available commands")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
        
    print(f"[DEBUG] Message reçu: {message.content} de {message.author}")
    
    await client.process_commands(message)

@client.command()
async def setup(ctx):
    if has_staff_role(ctx):
        embed = discord.Embed(title="🔧 Configuration du Support", description="Cliquez sur le bouton pour configurer le système de tickets.", color=discord.Color.blue())
        await ctx.send(embed=embed, view=TicketSetupView())
        print(f"[OK] Setup command executed by {ctx.author.name}")
    else:
        await ctx.send("❌ Vous n'avez pas la permission d'utiliser cette commande. Seuls les membres du staff peuvent l'utiliser.")
        print(f"[WARNING] User {ctx.author.name} tried to use setup command without permission")


@client.command(name="categories")
async def categories_command(ctx):
    embed = discord.Embed(
        title="📁 Catégories de Tickets",
        description="Voici les catégories de tickets disponibles",
        color=discord.Color.blue()
    )
    
    if not TICKET_CATEGORIES:
        embed.add_field(name="Aucune catégorie", value="Aucune catégorie de ticket n'est configurée.", inline=False)
    else:
        categories_list = "\n".join([f"• {category}" for category in TICKET_CATEGORIES])
        embed.add_field(name="Catégories disponibles", value=categories_list, inline=False)
    
    await ctx.send(embed=embed)

@client.command(name="addcategory")
async def add_category_command(ctx, *, category_name=None):
    if not has_staff_role(ctx):
        await ctx.send("❌ Vous n'avez pas la permission d'utiliser cette commande. Seuls les membres du staff peuvent l'utiliser.")
        print(f"[WARNING] User {ctx.author.name} tried to use addcategory command without permission")
        return
    
    if not category_name:
        await ctx.send("❌ Veuillez spécifier un nom pour la catégorie. Exemple: `!addcategory Demande de Partenariat`")
        return

    if category_name in TICKET_CATEGORIES:
        await ctx.send(f"❌ La catégorie '{category_name}' existe déjà.")
        return
    
    TICKET_CATEGORIES.append(category_name)
    
    if save_ticket_categories():
        try:
            staff_role = discord.utils.get(ctx.guild.roles, id=STAFF_ROLE_ID)
            
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            }
            
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            
            new_category = await ctx.guild.create_category(name=category_name, overwrites=overwrites)
            CATEGORY_IDS[category_name] = new_category.id
            
            await ctx.send(f"✅ Catégorie '{category_name}' ajoutée avec succès et créée sur le serveur.")
        except Exception as e:
            await ctx.send(f"⚠️ Catégorie '{category_name}' ajoutée, mais erreur lors de la création sur le serveur: {e}")
    else:
        await ctx.send(f"⚠️ Erreur lors de la sauvegarde des catégories.")

@client.command(name="delcategory")
async def del_category_command(ctx, *, category_name=None):
    if not has_staff_role(ctx):
        await ctx.send("❌ Vous n'avez pas la permission d'utiliser cette commande. Seuls les membres du staff peuvent l'utiliser.")
        print(f"[WARNING] User {ctx.author.name} tried to use delcategory command without permission")
        return
    
    if not category_name:
        await ctx.send("❌ Veuillez spécifier le nom de la catégorie à supprimer. Exemple: `!delcategory Demande de Partenariat`")
        return
    
    if category_name not in TICKET_CATEGORIES:
        await ctx.send(f"❌ La catégorie '{category_name}' n'existe pas.")
        return
    
    confirmation_msg = await ctx.send(f"⚠️ Êtes-vous sûr de vouloir supprimer la catégorie '{category_name}' ? Cette action ne supprimera pas la catégorie Discord, seulement l'option dans le système de tickets. Répondez avec 'oui' pour confirmer.")
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["oui", "non", "yes", "no"]
    
    try:
        response = await client.wait_for('message', check=check, timeout=30.0)
        
        if response.content.lower() in ["oui", "yes"]:
            TICKET_CATEGORIES.remove(category_name)
            
            if category_name in CATEGORY_IDS:
                del CATEGORY_IDS[category_name]
            
            if save_ticket_categories():
                await ctx.send(f"✅ Catégorie '{category_name}' supprimée avec succès.")
            else:
                await ctx.send(f"⚠️ Erreur lors de la sauvegarde des catégories.")
        else:
            await ctx.send("\u2139\ufe0f Suppression annulée.")
    
    except asyncio.TimeoutError:
        await ctx.send("\u23f0 Temps écoulé. Suppression annulée.")
        return

client.run(TOKEN)