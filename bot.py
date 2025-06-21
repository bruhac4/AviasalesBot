
# bot.py — основной код Discord-бота для управления рейсами

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

# 🔧 Настройки
ALLOWED_ROLE_IDS = [1323420440919670908, 1330492203969282129]  # ← Замени на ID своих ролей
FLIGHT_CHANNEL_ID = 1385932180005458011  # ← Замени на ID канала, куда отправлять рейсы

ROLE_CONFIG = {
    "pilot": {"label": "Пилот", "emoji": "✈️", "limit": 1},
    "copilot": {"label": "Ко-пилот", "emoji": "✈️", "limit": 1},
    "dispatcher": {"label": "Диспетчер", "emoji": "🎧", "limit": 2},
    "ground": {"label": "Наземная служба", "emoji": "🚨", "limit": 5},
    "steward": {"label": "Стюард", "emoji": "🚻", "limit": 3},
    "passenger": {"label": "Пассажир", "emoji": "🧳", "limit": None},
}

active_flights = {}  # ID: {data}

class RoleView(discord.ui.View):
    def __init__(self, flight_id):
        super().__init__(timeout=None)
        self.flight_id = flight_id
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        for key, info in ROLE_CONFIG.items():
            self.add_item(self.RoleButton(key, info))
        self.add_item(self.CancelButton())
    
    class RoleButton(discord.ui.Button):
        def __init__(self, key, info):
            super().__init__(label=info["label"], emoji=info["emoji"], style=discord.ButtonStyle.primary)
            self.role_key = key

        async def callback(self, interaction: discord.Interaction):
            flight = active_flights.get(interaction.message.id)
            if not flight:
                await interaction.response.send_message("Рейс не найден.", ephemeral=True)
                return

            if interaction.user.id in flight["users"]:
                await interaction.response.send_message("Вы уже зарегистрированы.", ephemeral=True)
                return

            limit = ROLE_CONFIG[self.role_key]["limit"]
            if limit is not None and len(flight["roles"][self.role_key]) >= limit:
                await interaction.response.send_message("Все места заняты.", ephemeral=True)
                return

            for k in flight["roles"]:
                flight["roles"][k] = [u for u in flight["roles"][k] if u != interaction.user.mention]

            for k in list(flight["users"].values()):
                if k == interaction.user.id:
                    flight["users"].pop(k, None)

            flight["roles"][self.role_key].append(interaction.user.mention)
            flight["users"][interaction.user.id] = self.role_key
            await interaction.message.edit(embed=generate_embed(flight), view=self.view)
            await interaction.response.send_message("Вы успешно записаны.", ephemeral=True)

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Отменить роль", emoji="⛔️", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            flight = active_flights.get(interaction.message.id)
            if not flight:
                await interaction.response.send_message("Рейс не найден.", ephemeral=True)
                return

            role_key = flight["users"].get(interaction.user.id)
            if not role_key:
                await interaction.response.send_message("Вы не записаны.", ephemeral=True)
                return

            flight["roles"][role_key].remove(interaction.user.mention)
            del flight["users"][interaction.user.id]
            await interaction.message.edit(embed=generate_embed(flight), view=self.view)
            await interaction.response.send_message("Роль удалена.", ephemeral=True)

def generate_embed(flight):
    roles_text = "\n".join([
        f"{ROLE_CONFIG[k]['emoji']} {ROLE_CONFIG[k]['label']}: {', '.join(v) if v else 'не назначено'}"
        for k, v in flight["roles"].items()
    ])
    return discord.Embed(
        title=f"🛫 Рейс {flight['id']}",
        description=(
            f"**Откуда:** {flight['from']}\n"
            f"**Куда:** {flight['to']}\n"
            f"**Пересадка:** {flight['transfer']}\n"
            f"**Запасной аэропорт:** {flight['alt']}\n"
            f"**Время:** {flight['time']}\n"
            f"**Гейт:** {flight['gate']}\n\n" +
            roles_text
        ),
        color=discord.Color.blue()
    )

@bot.tree.command(name="рейс", description="Создать рейс")
@app_commands.describe(
    departure="Аэропорт вылета",
    arrival="Аэропорт прибытия",
    transfer="Пересадка",
    alternate="Запасной аэропорт",
    time="Время вылета",
    gate="Гейт"
)
async def рейс(interaction: discord.Interaction, departure: str, arrival: str, transfer: str, alternate: str, time: str, gate: str):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        await interaction.response.send_message("❌ Отказано в доступе.", ephemeral=True)
        return

    flight_id = random.randint(1000, 9999)
    embed = discord.Embed(title="Создание рейса...", description="Ожидайте...", color=discord.Color.blue())

    channel = bot.get_channel(FLIGHT_CHANNEL_ID)
    msg = await channel.send(embed=embed)

    active_flights[msg.id] = {
        "id": flight_id,
        "from": departure,
        "to": arrival,
        "transfer": transfer,
        "alt": alternate,
        "time": time,
        "gate": gate,
        "message": msg,
        "roles": {k: [] for k in ROLE_CONFIG},
        "users": {}
    }
    view = RoleView(flight_id)
    await msg.edit(embed=generate_embed(active_flights[msg.id]), view=view)
    await interaction.response.send_message(f"✅ Рейс создан. ID: {flight_id}", ephemeral=True)

@bot.tree.command(name="активные", description="Показать активные рейсы")
async def активные(interaction: discord.Interaction):
    if not active_flights:
        await interaction.response.send_message("❌ Активных рейсов нет.", ephemeral=True)
        return

    text = "\n".join([f"N.{flight['id']} | {flight['from']} → {flight['to']} (гейт {flight['gate']})" for flight in active_flights.values()])
    view = discord.ui.View()
    for msg_id, flight in active_flights.items():
        view.add_item(discord.ui.Button(label=f"N.{flight['id']}", style=discord.ButtonStyle.success, custom_id=f"show_{msg_id}"))

    await interaction.response.send_message(f"📋 Активные рейсы:\n{text}", view=view, ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    try:
        await bot.tree.sync()
        print("🔁 Slash-команды синхронизированы")
    except Exception as e:
        print(f"Ошибка при синхронизации: {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data["custom_id"].startswith("show_"):
            msg_id = int(interaction.data["custom_id"].split("_")[1])
            flight = active_flights.get(msg_id)
            if not flight:
                await interaction.response.send_message("Рейс не найден.", ephemeral=True)
                return

            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Закрыть регистрацию", style=discord.ButtonStyle.danger, custom_id=f"close_{msg_id}"))
            view.add_item(discord.ui.Button(label="Изменить информацию", style=discord.ButtonStyle.primary, custom_id=f"edit_{msg_id}"))
            view.add_item(discord.ui.Button(label="Сбросить рейс", style=discord.ButtonStyle.danger, custom_id=f"delete_{msg_id}"))

            await interaction.response.send_message(embed=generate_embed(flight), view=view, ephemeral=True)
            return

        elif interaction.data["custom_id"].startswith("delete_"):
            msg_id = int(interaction.data["custom_id"].split("_")[1])
            flight = active_flights.pop(msg_id, None)
            if flight:
                await flight["message"].delete()
                await interaction.response.send_message("🗑️ Рейс удалён.", ephemeral=True)
            else:
                await interaction.response.send_message("Рейс не найден.", ephemeral=True)
            return

        elif interaction.data["custom_id"].startswith("close_"):
            msg_id = int(interaction.data["custom_id"].split("_")[1])
            flight = active_flights.get(msg_id)
            if flight:
                await flight["message"].edit(view=None)
                await interaction.response.send_message("🔒 Регистрация закрыта.", ephemeral=True)
            return

bot.run(os.getenv("TOKEN"))
