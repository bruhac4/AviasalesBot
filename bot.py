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

# Ваши ID (указанные вами)
ALLOWED_ROLE_IDS = [1323420440919670908, 1330492203969282129]  # Роли которые могут создавать рейсы
FLIGHT_CHANNEL_ID = 1385932180005458011  # ID канала для рейсов

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
            flight = None
            for f in active_flights.values():
                if f["id"] == self.view.flight_id:
                    flight = f
                    break
            
            if not flight:
                return await interaction.response.send_message("Рейс не найден.", ephemeral=True)

            if interaction.user.id in flight["users"]:
                return await interaction.response.send_message("Вы уже зарегистрированы.", ephemeral=True)

            if ROLE_CONFIG[self.role_key]["limit"] is not None and \
               len(flight["roles"][self.role_key]) >= ROLE_CONFIG[self.role_key]["limit"]:
                return await interaction.response.send_message("Мест больше нет.", ephemeral=True)

            # Удаляем старую роль если была
            for r, users in flight["roles"].items():
                if interaction.user.mention in users:
                    users.remove(interaction.user.mention)
                    flight["users"].pop(interaction.user.id, None)

            flight["roles"][self.role_key].append(interaction.user.mention)
            flight["users"][interaction.user.id] = self.role_key
            await interaction.message.edit(embed=generate_embed(flight), view=RoleView(flight["id"]))
            await interaction.response.send_message(f"Вы записаны как {ROLE_CONFIG[self.role_key]['label']}.", ephemeral=True)

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
            await interaction.response.send_message("Ваша роль удалена.", ephemeral=True)

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
    embed = discord.Embed(title=f"🛫 Рейс {flight['id']}", description=info + roles, color=discord.Color.blue())
    embed.set_footer(text="Для записи нажмите на кнопку ниже")
    return embed

@bot.tree.command(name="рейс", description="Создать новый рейс")
@app_commands.describe(
    departure="Аэропорт вылета",
    arrival="Аэропорт прибытия",
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
        # Проверка прав
        if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
            return await interaction.response.send_message("❌ У вас нет прав для создания рейсов!", ephemeral=True)

        # Отправляем "бот думает" чтобы избежать таймаута
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Генерируем ID рейса
        flight_id = random.randint(1000, 9999)
        
        # Получаем канал для рейсов
        channel = bot.get_channel(FLIGHT_CHANNEL_ID)
        if not channel:
            return await interaction.followup.send("❌ Канал для рейсов не найден!", ephemeral=True)

        # Создаем временное сообщение
        temp_embed = discord.Embed(title="🛫 Создание рейса...", description="Пожалуйста, подождите...", color=discord.Color.blue())
        msg = await channel.send(
            content=f"✈️ @everyone\n{interaction.user.mention} создал новый рейс!",
            embed=temp_embed
        )

        # Создаем данные рейса
        flight_data = {
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

        # Сохраняем рейс
        active_flights[msg.id] = flight_data

        # Обновляем сообщение с кнопками
        await msg.edit(embed=generate_embed(flight_data), view=RoleView(flight_id))
        
        # Отправляем подтверждение создателю
        await interaction.followup.send(
            f"✅ Рейс успешно создан!\n"
            f"**ID:** {flight_id}\n"
            f"**Маршрут:** {departure} → {arrival}\n"
            f"**Канал:** {channel.mention}",
            ephemeral=True
        )

    except Exception as e:
        print(f"Ошибка при создании рейса: {e}")
        await interaction.followup.send(
            f"❌ Произошла ошибка при создании рейса:\n```{e}```",
            ephemeral=True
        )

@bot.tree.command(name="активные_рейсы", description="Показать активные рейсы")
async def active_flights(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
        
        if not active_flights:
            return await interaction.followup.send("ℹ️ Сейчас нет активных рейсов.", ephemeral=True)

        flights_list = []
        for flight in active_flights.values():
            flights_list.append(
                f"**Рейс {flight['id']}**\n"
                f"🛫 {flight['from']} → 🛬 {flight['to']}\n"
                f"⏱ {flight['time']} | 🚪 {flight['gate']}\n"
            )

        embed = discord.Embed(
            title="✈️ Активные рейсы",
            description="\n".join(flights_list),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Всего активных рейсов: {len(active_flights)}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"Ошибка при показе активных рейсов: {e}")
        await interaction.followup.send(
            f"❌ Произошла ошибка:\n```{e}```",
            ephemeral=True
        )

class FlightControlView(discord.ui.View):
    def __init__(self, msg_id):
        super().__init__(timeout=None)
        self.msg_id = msg_id
        
        close_btn = discord.ui.Button(
            label="Закрыть регистрацию", 
            style=discord.ButtonStyle.danger, 
            custom_id=f"close_{msg_id}"
        )
        delete_btn = discord.ui.Button(
            label="Удалить рейс", 
            style=discord.ButtonStyle.danger, 
            custom_id=f"delete_{msg_id}"
        )
        
        self.add_item(close_btn)
        self.add_item(delete_btn)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type == discord.InteractionType.component:
        try:
            custom_id = interaction.data.get("custom_id", "")
            
            if custom_id.startswith("show_"):
                msg_id = int(custom_id.split("_")[1])
                flight = active_flights.get(msg_id)
                if not flight:
                    await interaction.response.defer(ephemeral=True)
                    return await interaction.followup.send("❌ Рейс не найден!", ephemeral=True)

                view = FlightControlView(msg_id)
                await interaction.response.send_message(
                    embed=generate_embed(flight), 
                    view=view, 
                    ephemeral=True
                )
                
            elif custom_id.startswith("delete_"):
                msg_id = int(custom_id.split("_")[1])
                flight = active_flights.pop(msg_id, None)
                if flight:
                    await interaction.response.defer(ephemeral=True)
                    try:
                        await flight["message"].delete()
                        await interaction.followup.send("✅ Рейс успешно удалён!", ephemeral=True)
                    except Exception as e:
                        await interaction.followup.send(
                            f"❌ Ошибка при удалении рейса:\n```{e}```", 
                            ephemeral=True
                        )

            elif custom_id.startswith("close_"):
                msg_id = int(custom_id.split("_")[1])
                flight = active_flights.get(msg_id)
                if flight:
                    await interaction.response.defer(ephemeral=True)
                    try:
                        await flight["message"].edit(view=None)
                        await interaction.followup.send("✅ Регистрация на рейс закрыта!", ephemeral=True)
                    except Exception as e:
                        await interaction.followup.send(
                            f"❌ Ошибка при закрытии регистрации:\n```{e}```", 
                            ephemeral=True
                        )
        except Exception as e:
            print(f"Ошибка в обработке взаимодействия: {e}")
            try:
                await interaction.response.send_message(
                    "❌ Произошла ошибка при обработке запроса!", 
                    ephemeral=True
                )
            except:
                pass

@bot.event
async def on_ready():
    print(f"✅ Бот успешно запущен как {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации команд: {e}")

# Запуск бота
bot.run(os.getenv("TOKEN"))
