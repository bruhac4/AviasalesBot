# bot.py

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

ALLOWED_ROLE_IDS = [123456789012345678]  # ← Замени на свои
FLIGHT_CHANNEL_ID = 123456789012345678   # ← Замени на ID канала

ROLE_CONFIG = {
    "pilot": {"label": "Пилот", "emoji": "✈️", "limit": 1},
    "copilot": {"label": "Ко-пилот", "emoji": "✈️", "limit": 1},
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
        for key in ROLE_CONFIG:
            self.add_item(self.RoleButton(key))
        self.add_item(self.CancelButton())

    class RoleButton(discord.ui.Button):
        def __init__(self, role_key):
            info = ROLE_CONFIG[role_key]
            super().__init__(label=info["label"], emoji=info["emoji"], style=discord.ButtonStyle.primary)
            self.role_key = role_key

        async def callback(self, interaction: discord.Interaction):
            flight = active_flights.get(interaction.message.id)
            if not flight:
                return await safe_send(interaction, "Рейс не найден.")

            if interaction.user.id in flight["users"]:
                return await safe_send(interaction, "Вы уже зарегистрированы.")

            if ROLE_CONFIG[self.role_key]["limit"] is not None and \
               len(flight["roles"][self.role_key]) >= ROLE_CONFIG[self.role_key]["limit"]:
                return await safe_send(interaction, "Мест больше нет.")

            # удалить старую роль
            for r, users in flight["roles"].items():
                if interaction.user.mention in users:
                    users.remove(interaction.user.mention)
                    flight["users"].pop(interaction.user.id, None)

            flight["roles"][self.role_key].append(interaction.user.mention)
            flight["users"][interaction.user.id] = self.role_key
            await interaction.message.edit(embed=generate_embed(flight), view=self.view)
            await safe_send(interaction, "Вы записаны.")

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Отменить роль", emoji="⛔️", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            for flight in active_flights.values():
                if interaction.user.id in flight["users"]:
                    role = flight["users"].pop(interaction.user.id)
                    flight["roles"][role].remove(interaction.user.mention)
                    await flight["message"].edit(embed=generate_embed(flight), view=self.view)
                    return await safe_send(interaction, "Роль удалена.")
            await safe_send(interaction, "Вы не зарегистрированы.")

def generate_embed(flight):
    info = (
        f"**Откуда:** {flight['from']}\n"
        f"**Куда:** {flight['to']}\n"
        f"**Пересадка:** {flight['transfer']}\n"
        f"**Запасной аэропорт:** {flight['alt']}\n"
        f"**Время:** {flight['time']}\n"
        f"**Гейт:** {flight['gate']}\n\n"
    )
    roles = "\n".join([
        f"{ROLE_CONFIG[k]['emoji']} {ROLE_CONFIG[k]['label']}: {', '.join(v) if v else 'не назначено'}"
        for k, v in flight["roles"].items()
    ])
    return discord.Embed(title=f"🛫 Рейс {flight['id']}", description=info + roles, color=discord.Color.blue())

async def safe_send(interaction, text):
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)

@bot.tree.command(name="рейс", description="Создать рейс")
@app_commands.describe(
    departure="Аэропорт вылета",
    arrival="Аэропорт прибытия",
    transfer="Пересадка",
    alternate="Запасной аэропорт",
    time="Время",
    gate="Гейт"
)
async def рейс(interaction: discord.Interaction, departure: str, arrival: str, transfer: str, alternate: str, time: str, gate: str):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await safe_send(interaction, "❌ Отказано в доступе.")

    flight_id = random.randint(1000, 9999)
    channel = await interaction.guild.fetch_channel(FLIGHT_CHANNEL_ID)

    msg = await channel.send(
        content=f"[✈] @everyone\n[✈] {interaction.user.mention} создал новый рейс!",
        embed=discord.Embed(title="Создание рейса...", description="Подождите...", color=discord.Color.blue())
    )

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

    await msg.edit(embed=generate_embed(active_flights[msg.id]), view=RoleView(flight_id))
    await safe_send(interaction, f"✅ Рейс создан. ID: {flight_id}")

@bot.tree.command(name="активные", description="Список активных рейсов")
async def активные(interaction: discord.Interaction):
    if not active_flights:
        return await safe_send(interaction, "Нет активных рейсов.")

    view = discord.ui.View()
    for msg_id, flight in active_flights.items():
        view.add_item(discord.ui.Button(label=f"N.{flight['id']}", style=discord.ButtonStyle.success, custom_id=f"show_{msg_id}"))

    list_text = "\n".join([f"N.{f['id']} | {f['from']} → {f['to']} (гейт {f['gate']})" for f in active_flights.values()])
    await safe_send(interaction, f"📋 Активные рейсы:\n{list_text}")
    interaction.followup.send(view=view, ephemeral=True)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        cid = interaction.data.get("custom_id", "")
        msg_id = int(cid.split("_")[1]) if "_" in cid else None

        if cid.startswith("show_") and msg_id in active_flights:
            flight = active_flights[msg_id]
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Закрыть регистрацию", style=discord.ButtonStyle.danger, custom_id=f"close_{msg_id}"))
            view.add_item(discord.ui.Button(label="Сбросить рейс", style=discord.ButtonStyle.danger, custom_id=f"delete_{msg_id}"))
            await safe_send(interaction, "", embed=generate_embed(flight))
            await interaction.followup.send(view=view, ephemeral=True)

        elif cid.startswith("delete_") and msg_id in active_flights:
            flight = active_flights.pop(msg_id)
            await flight["message"].delete()
            await safe_send(interaction, "🗑️ Рейс удалён.")

        elif cid.startswith("close_") and msg_id in active_flights:
            flight = active_flights[msg_id]
            await flight["message"].edit(view=None)
            await safe_send(interaction, "🔒 Регистрация закрыта.")

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    try:
        await bot.tree.sync()
        print("🔁 Slash-команды синхронизированы")
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")

bot.run(os.getenv("TOKEN"))
