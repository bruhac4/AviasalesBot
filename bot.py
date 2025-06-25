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
    "pilot": {"label": "Пилот", "emoji": "✈", "limit": 1},
    "copilot": {"label": "Ко-пилот", "emoji": "✈", "limit": 1},
    "dispatcher": {"label": "Диспетчер", "emoji": "🎧", "limit": 2},
    "ground": {"label": "Наземная служба", "emoji": "🚨", "limit": 5},
    "steward": {"label": "Стюард", "emoji": "🚻", "limit": 3},
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
                label=info["label"],
                emoji=info["emoji"],
                style=discord.ButtonStyle.primary,
                custom_id=f"role_{role_key}"
            )
            self.role_key = role_key

        async def callback(self, interaction: discord.Interaction):
            flight = next((f for f in active_flights.values() if f["id"] == self.view.flight_id), None)
            if not flight:
                return await interaction.response.send_message("Рейс не найден.", ephemeral=True)
            
            if interaction.user.id in flight["users"]:
                if flight["users"][interaction.user.id] == self.role_key:
                    return await interaction.response.send_message("Вы уже имеете эту роль.", ephemeral=True)
            
            if ROLE_CONFIG[self.role_key]["limit"] and len(flight["roles"][self.role_key]) >= ROLE_CONFIG[self.role_key]["limit"]:
                return await interaction.response.send_message("Лимит на эту роль достигнут.", ephemeral=True)

            if interaction.user.id in flight["users"]:
                old_role = flight["users"][interaction.user.id]
                flight["roles"][old_role].remove(interaction.user.mention)
            
            flight["roles"][self.role_key].append(interaction.user.mention)
            flight["users"][interaction.user.id] = self.role_key
            
            await interaction.message.edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message(f"Теперь вы {ROLE_CONFIG[self.role_key]['label']}!", ephemeral=True)

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                label="Отменить роль",
                emoji="❌",
                style=discord.ButtonStyle.danger,
                custom_id="cancel_role"
            )

        async def callback(self, interaction: discord.Interaction):
            flight = next((f for f in active_flights.values() if interaction.user.id in f["users"]), None)
            if not flight:
                return await interaction.response.send_message("Вы не зарегистрированы в рейсе.", ephemeral=True)
            
            role = flight["users"].pop(interaction.user.id)
            flight["roles"][role].remove(interaction.user.mention)
            
            await flight["message"].edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message("Вы больше не участвуете в рейсе.", ephemeral=True)

def generate_embed(flight):
    info = (
        f"**Откуда:** {flight['from']}\n"
        f"**Куда:** {flight['to']}\n"
        f"**Пересадка:** {flight['transfer']}\n"
        f"**Запасной аэропорт:** {flight['alt']}\n"
        f"**Время:** {flight['time']}\n"
        f"**Гейт:** {flight['gate']}\n\n"
    )
    roles = "\n".join([f"{ROLE_CONFIG[k]['emoji']} {ROLE_CONFIG[k]['label']}: {', '.join(v) if v else 'нет'}"
                      for k, v in flight["roles"].items()])
    embed = discord.Embed(title=f"🛫 Рейс {flight['id']}", description=info + roles, color=0x3498db)
    embed.set_footer(text="Нажмите кнопку для выбора роли")
    return embed

@bot.tree.command(name="рейс", description="Создать новый рейс")
@app_commands.describe(
    departure="Откуда вылетаем",
    arrival="Куда прилетаем",
    transfer="Пересадка (если есть)",
    alternate="Запасной аэропорт",
    time="Время вылета",
    gate="Номер гейта"
)
async def create_flight(interaction: discord.Interaction, 
                      departure: str, 
                      arrival: str, 
                      transfer: str, 
                      alternate: str, 
                      time: str, 
                      gate: str):
    try:
        if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
            return await interaction.response.send_message("❌ У вас нет прав для создания рейсов!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        flight_id = random.randint(1000, 9999)
        channel = bot.get_channel(FLIGHT_CHANNEL_ID)
        
        if not channel:
            return await interaction.followup.send("❌ Канал для рейсов не найден!", ephemeral=True)

        flight_data = {
            "id": flight_id,
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

        await interaction.followup.send(f"✅ Рейс {flight_id} создан в {channel.mention}!", ephemeral=True)

    except Exception as e:
        print(f"Ошибка: {e}")
        await interaction.followup.send(f"❌ Ошибка при создании рейса: {e}", ephemeral=True)

@bot.tree.command(name="активные", description="Показать активные рейсы")
async def show_active(interaction: discord.Interaction):
    try:
        if not active_flights:
            return await interaction.response.send_message("Сейчас нет активных рейсов.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        flights_list = []
        for flight in active_flights.values():
            flights_list.append(
                f"**Рейс {flight['id']}**\n"
                f"🛫 {flight['from']} → {flight['to']}\n"
                f"⏰ {flight['time']} | 🚪 {flight['gate']}\n"
            )

        embed = discord.Embed(
            title="✈️ Активные рейсы",
            description="\n".join(flights_list),
            color=0x3498db
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"Ошибка: {e}")
        await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Бот {bot.user} готов к работе!")
    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")

bot.run(os.getenv("TOKEN"))
