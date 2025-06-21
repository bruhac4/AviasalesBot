import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

ALLOWED_ROLE_IDS = [123456789012345678, 987654321098765432]  # ← ВСТАВЬ СВОИ РОЛИ
FLIGHT_CHANNEL_ID = 123456789012345678  # ← ВСТАВЬ ID КАНАЛА

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
        for key, info in ROLE_CONFIG.items():
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
                return await interaction.response.send_message("Рейс не найден.", ephemeral=True)

            if interaction.user.id in flight["users"]:
                return await interaction.response.send_message("Вы уже зарегистрированы.", ephemeral=True)

            if ROLE_CONFIG[self.role_key]["limit"] is not None and \
               len(flight["roles"][self.role_key]) >= ROLE_CONFIG[self.role_key]["limit"]:
                return await interaction.response.send_message("Мест больше нет.", ephemeral=True)

            # удалим старую роль если была
            for r, users in flight["roles"].items():
                if interaction.user.mention in users:
                    users.remove(interaction.user.mention)
                    flight["users"].pop(interaction.user.id, None)

            flight["roles"][self.role_key].append(interaction.user.mention)
            flight["users"][interaction.user.id] = self.role_key
            await interaction.message.edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message("Вы записаны.", ephemeral=True)

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Отменить роль", emoji="⛔️", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            flight = None
            for f in active_flights.values():
                if interaction.user.id in f["users"]:
                    flight = f
                    break
            
            if not flight:
                return await interaction.response.send_message("Вы не зарегистрированы.", ephemeral=True)

            role = flight["users"].pop(interaction.user.id)
            flight["roles"][role].remove(interaction.user.mention)
            await flight["message"].edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message("Роль удалена.", ephemeral=True)

def generate_embed(flight):
    info = (
        f"**Откуда:** {flight['from']}\n"
        f"**Куда:** {flight['to']}\n"
        f"**Пересадка:** {flight['transfer']}\n"
        f"**Запасной аэропорт:** {flight['alt']}\n"
        f"**Время:** {flight['time']}\n"
        f"**Гейт:** {flight['gate']}\n\n"
    )
    roles = "\n".join([f"{ROLE_CONFIG[k]['emoji']} {ROLE_CONFIG[k]['label']}: {', '.join(v) if v else 'не назначено'}"
                       for k, v in flight["roles"].items()])
    return discord.Embed(title=f"🛫 Рейс {flight['id']}", description=info + roles, color=discord.Color.blue())

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
        return await interaction.response.send_message("❌ Отказано в доступе.", ephemeral=True)

    flight_id = random.randint(1000, 9999)
    channel = bot.get_channel(FLIGHT_CHANNEL_ID)
    if not channel:
        return await interaction.response.send_message("Канал не найден.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)  # Добавлено для предотвращения таймаута

    try:
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
        await interaction.followup.send(f"✅ Рейс создан. ID: {flight_id}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка при создании рейса: {e}", ephemeral=True)

@bot.tree.command(name="активные", description="Список активных рейсов")
async def активные(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # Добавлено для предотвращения таймаута
    
    if not active_flights:
        return await interaction.followup.send("Нет активных рейсов.", ephemeral=True)

    list_text = "\n".join([f"N.{f['id']} | {f['from']} → {f['to']} (гейт {f['gate']})" for f in active_flights.values()])
    await interaction.followup.send(f"📋 Активные рейсы:\n{list_text}", ephemeral=True)

class FlightControlView(discord.ui.View):
    def __init__(self, msg_id):
        super().__init__()
        self.msg_id = msg_id
        
        self.add_item(discord.ui.Button(label="Закрыть регистрацию", style=discord.ButtonStyle.danger, custom_id=f"close_{msg_id}"))
        self.add_item(discord.ui.Button(label="Изменить информацию", style=discord.ButtonStyle.primary, disabled=True))
        self.add_item(discord.ui.Button(label="Сбросить рейс", style=discord.ButtonStyle.danger, custom_id=f"delete_{msg_id}"))

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        custom_id = interaction.data.get("custom_id", "")
        
        if custom_id.startswith("show_"):
            msg_id = int(custom_id.split("_")[1])
            flight = active_flights.get(msg_id)
            if not flight:
                await interaction.response.defer(ephemeral=True)
                return await interaction.followup.send("Рейс не найден.", ephemeral=True)

            view = FlightControlView(msg_id)
            await interaction.response.send_message(embed=generate_embed(flight), view=view, ephemeral=True)
            
        elif custom_id.startswith("delete_"):
            msg_id = int(custom_id.split("_")[1])
            flight = active_flights.pop(msg_id, None)
            if flight:
                await interaction.response.defer(ephemeral=True)
                try:
                    await flight["message"].delete()
                    await interaction.followup.send("🗑️ Рейс удалён.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"Ошибка при удалении: {e}", ephemeral=True)

        elif custom_id.startswith("close_"):
            msg_id = int(custom_id.split("_")[1])
            flight = active_flights.get(msg_id)
            if flight:
                await interaction.response.defer(ephemeral=True)
                try:
                    await flight["message"].edit(view=None)
                    await interaction.followup.send("🔒 Регистрация закрыта.", ephemeral=True)
                except Exception as e:
                    await interaction.followup.send(f"Ошибка при закрытии: {e}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")

bot.run(os.getenv("TOKEN"))
