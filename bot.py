import discord
from discord.ext import commands
from discord import app_commands
import os
import random

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Ваши ID
ALLOWED_ROLE_IDS = [1323420440919670908, 1330492203969282129]  # Роли для создания рейсов
FLIGHT_CHANNEL_ID = 1385932180005458011  # Канал для рейсов

ROLE_CONFIG = {
    "pilot": {"label": "Пилот", "emoji": "👨‍✈️", "limit": 1},
    "copilot": {"label": "Ко-пилот", "emoji": "👨‍✈️", "limit": 1},
    "dispatcher": {"label": "Диспетчер", "emoji": "🎧", "limit": 2},
    "steward": {"label": "Бортпроводник", "emoji": "👨‍💼", "limit": 3},
    "ground": {"label": "Наземная служба", "emoji": "🚨", "limit": 5},
    "passenger": {"label": "Пассажир", "emoji": "🧳", "limit": None},
}

active_flights = {}

class RoleView(discord.ui.View):
    def __init__(self, flight_id):
        super().__init__(timeout=None)
        self.flight_id = flight_id
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for key, info in ROLE_CONFIG.items():
            self.add_item(self.RoleButton(key))
        self.add_item(self.CancelButton())

    class RoleButton(discord.ui.Button):
        def __init__(self, role_key):
            info = ROLE_CONFIG[role_key]
            super().__init__(
                label=f"{info['label']}",
                style=discord.ButtonStyle.primary,
                emoji=info["emoji"],
                custom_id=f"role_{role_key}"
            )
            self.role_key = role_key

        async def callback(self, interaction: discord.Interaction):
            flight = next((f for f in active_flights.values() if f["id"] == self.view.flight_id), None)
            if not flight:
                return await interaction.response.send_message("[❌] Рейс не найден.", ephemeral=True)
            
            if interaction.user.id in flight["users"]:
                if flight["users"][interaction.user.id] == self.role_key:
                    return await interaction.response.send_message("[⛔] Вы уже имеете эту роль.", ephemeral=True)
            
            if ROLE_CONFIG[self.role_key]["limit"] and len(flight["roles"][self.role_key]) >= ROLE_CONFIG[self.role_key]["limit"]:
                return await interaction.response.send_message("[⚠️] Лимит на эту роль достигнут.", ephemeral=True)

            if interaction.user.id in flight["users"]:
                old_role = flight["users"][interaction.user.id]
                flight["roles"][old_role].remove(interaction.user.mention)
            
            flight["roles"][self.role_key].append(interaction.user.mention)
            flight["users"][interaction.user.id] = self.role_key
            
            await interaction.message.edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message(f"[✅] Теперь вы {ROLE_CONFIG[self.role_key]['label']}!", ephemeral=True)

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                label="Отменить роль",
                style=discord.ButtonStyle.danger,
                emoji="❌",
                custom_id="cancel_role"
            )

        async def callback(self, interaction: discord.Interaction):
            flight = next((f for f in active_flights.values() if interaction.user.id in f["users"]), None)
            if not flight:
                return await interaction.response.send_message("[❌] Вы не зарегистрированы в рейсе.", ephemeral=True)
            
            role = flight["users"].pop(interaction.user.id)
            flight["roles"][role].remove(interaction.user.mention)
            
            await flight["message"].edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message("[✅] Вы больше не участвуете в рейсе.", ephemeral=True)

def generate_embed(flight):
    flight_info = (
        f"**Модель самолёта:** {flight['aircraft']}\n"
        f"**Аэропорт вылета:** {flight['from']}\n"
        f"**Аэропорт прибытия:** {flight['to']}\n"
        f"**Пересадка:** {flight['transfer']}\n"
        f"**Запасной аэропорт:** {flight['alt']}\n\n"
        f"**Время:** {flight['time']}\n"
        f"**Гейт:** {flight['gate']}\n\n"
    )
    
    roles_info = []
    for key, info in ROLE_CONFIG.items():
        members = flight["roles"][key]
        roles_info.append(f"{info['emoji']} **{info['label']}:**")
        if members:
            for member in members:
                roles_info.append(f"- {member}")
        else:
            roles_info.append("- Не назначено")
        roles_info.append("")  # Пустая строка между ролями
    
    description = flight_info + "\n".join(roles_info)
    
    embed = discord.Embed(
        title=f"✈️ Рейс {flight['id']} | {flight['from']} → {flight['to']}",
        description=description,
        color=0x3498db
    )
    return embed

class FlightButton(discord.ui.Button):
    def __init__(self, flight_id):
        super().__init__(
            label=f"N.{flight_id}",
            style=discord.ButtonStyle.green,
            custom_id=f"show_{flight_id}"
        )
        self.flight_id = flight_id

    async def callback(self, interaction: discord.Interaction):
        flight = next((f for f in active_flights.values() if f["id"] == self.flight_id), None)
        if not flight:
            return await interaction.response.send_message("[❌] Рейс не найден.", ephemeral=True)
        
        view = FlightControlView(flight["message"].id)
        await interaction.response.send_message(
            embed=generate_embed(flight),
            view=view,
            ephemeral=True
        )

class FlightControlView(discord.ui.View):
    def __init__(self, msg_id):
        super().__init__(timeout=None)
        self.msg_id = msg_id
        
        close_btn = discord.ui.Button(
            label="Закрыть регистрацию",
            style=discord.ButtonStyle.primary,
            emoji="🔒",
            custom_id=f"close_{msg_id}"
        )
        delete_btn = discord.ui.Button(
            label="Удалить рейс",
            style=discord.ButtonStyle.primary,
            emoji="🗑️",
            custom_id=f"delete_{msg_id}"
        )
        
        close_btn.callback = self.close_callback
        delete_btn.callback = self.delete_callback
        
        self.add_item(close_btn)
        self.add_item(delete_btn)

    async def close_callback(self, interaction: discord.Interaction):
        flight = active_flights.get(self.msg_id)
        if flight:
            await interaction.response.defer(ephemeral=True)
            await flight["message"].edit(view=None)
            await interaction.followup.send("[✅] Регистрация на рейс закрыта!", ephemeral=True)

    async def delete_callback(self, interaction: discord.Interaction):
        flight = active_flights.pop(self.msg_id, None)
        if flight:
            await interaction.response.defer(ephemeral=True)
            await flight["message"].delete()
            await interaction.followup.send("[✅] Рейс успешно удалён!", ephemeral=True)

@bot.tree.command(name="рейс", description="Создать новый рейс")
@app_commands.describe(
    aircraft="Модель самолёта",
    departure="Аэропорт вылета",
    arrival="Аэропорт прибытия",
    transfer="Пересадка (если есть)",
    alternate="Запасной аэропорт",
    time="Время вылета",
    gate="Номер гейта"
)
async def create_flight(interaction: discord.Interaction, 
                      aircraft: str,
                      departure: str, 
                      arrival: str, 
                      transfer: str, 
                      alternate: str, 
                      time: str, 
                      gate: str):
    try:
        if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
            return await interaction.response.send_message("[❌] У вас нет прав для создания рейсов!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        flight_id = random.randint(1000, 9999)
        channel = bot.get_channel(FLIGHT_CHANNEL_ID)
        
        if not channel:
            return await interaction.followup.send("[❌] Канал для рейсов не найден!", ephemeral=True)

        flight_data = {
            "id": flight_id,
            "aircraft": aircraft,
            "from": departure,
            "to": arrival,
            "transfer": transfer,
            "alt": alternate,
            "time": time,
            "gate": gate,
            "roles": {k: [] for k in ROLE_CONFIG},
            "users": {}
        }

        view = RoleView(flight_id)
        msg = await channel.send(
            content=f"✈️ @everyone\n{interaction.user.mention} создал новый рейс!",
            embed=generate_embed(flight_data),
            view=view
        )

        flight_data["message"] = msg
        active_flights[msg.id] = flight_data

        await interaction.followup.send(f"[✅] Рейс {flight_id} создан в {channel.mention}!", ephemeral=True)

    except Exception as e:
        print(f"[❌] Ошибка: {e}")
        await interaction.followup.send(f"[❌] Ошибка при создании рейса: {str(e)}", ephemeral=True)

@bot.tree.command(name="активные_рейсы", description="Показать активные рейсы")
async def show_active_flights(interaction: discord.Interaction):
    try:
        if not active_flights:
            return await interaction.response.send_message("[ℹ️] Сейчас нет активных рейсов.", ephemeral=True)

        view = discord.ui.View(timeout=None)
        for flight in active_flights.values():
            view.add_item(FlightButton(flight["id"]))

        await interaction.response.send_message(
            "[📋] Выберите рейс для управления:",
            view=view,
            ephemeral=True
        )

    except Exception as e:
        print(f"[❌] Ошибка: {e}")
        await interaction.response.send_message(f"[❌] Ошибка: {str(e)}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"[✅] Бот {bot.user} готов к работе!")
    try:
        synced = await bot.tree.sync()
        print(f"[🔄] Синхронизировано {len(synced)} команд: {[cmd.name for cmd in synced]}")
    except Exception as e:
        print(f"[❌] Ошибка синхронизации: {e}")

bot.run(os.getenv("TOKEN"))
