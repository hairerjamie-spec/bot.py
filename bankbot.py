import discord
from discord.ext import commands, tasks
from datetime import datetime
import json
import os

# ================= CONFIG =================
DISCORD_TOKEN = "DEIN_BOT_TOKEN_HIER"
LOG_CHANNEL_ID = 123456789012345678
ADMIN_IDS = [123456789012345678]      # Optional: Admin-IDs für Admin-Befehle
CENTRAL_ACCOUNT_ID = 0                # Zentrales Konto für automatische Auszahlung
MONDAY_PAYOUT = 100                   # Betrag an zentrales Konto jeden Montag
VIP_BONUS = 0.10                      # 10% Bonuszinsen für VIP-Konten
CREDIT_INTEREST = 0.02                # 2% Kredit-Zinsen wöchentlich
TRANSACTION_FEE = 0.01                 # 1% Transaktionssteuer
# =========================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Daten speichern in JSON
if not os.path.exists("accounts.json"):
    with open("accounts.json", "w") as f:
        json.dump({}, f)

def load_accounts():
    with open("accounts.json", "r") as f:
        return json.load(f)

def save_accounts(data):
    with open("accounts.json", "w") as f:
        json.dump(data, f, indent=4)

# ---------------- HELPER ---------------- #
def get_account(user_id):
    accounts = load_accounts()
    if str(user_id) not in accounts:
        accounts[str(user_id)] = {
            "balance": 0,
            "loan": 0,
            "loan_timer": 0,      # für Mini-Loans Frist
            "savings": 0,
            "vip": False
        }
    return accounts

async def send_log(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(message)

def is_admin(ctx):
    return ctx.author.guild_permissions.administrator or ctx.author.id in ADMIN_IDS

# ---------------- COMMANDS ---------------- #

# Kontostand anzeigen
@bot.command()
async def balance(ctx):
    accounts = get_account(ctx.author.id)
    bal = accounts[str(ctx.author.id)]["balance"]
    loan = accounts[str(ctx.author.id)]["loan"]
    savings = accounts[str(ctx.author.id)]["savings"]
    vip = accounts[str(ctx.author.id)]["vip"]
    await ctx.reply(f"💶 Kontostand: {bal:.2f} €\n💳 Kredit: {loan:.2f} €\n💰 Sparkonto: {savings:.2f} €\n{'🌟 VIP-Konto' if vip else ''}")
    await send_log(f"📊 BALANCE – {ctx.author} prüfte Kontostand")

# Geld senden
@bot.command()
async def pay(ctx, member: discord.Member, amount: float):
    if amount <= 0:
        return await ctx.reply("❌ Betrag muss größer als 0 sein.")
    accounts = get_account(ctx.author.id)
    fee = amount * TRANSACTION_FEE
    total = amount + fee
    if accounts[str(ctx.author.id)]["balance"] < total:
        return await ctx.reply(f"❌ Du hast nicht genug Geld (inklusive {fee:.2f} € Transaktionsgebühr).")
    accounts[str(ctx.author.id)]["balance"] -= total
    target = get_account(member.id)
    target[str(member.id)]["balance"] += amount
    save_accounts(accounts)
    save_accounts(target)
    await ctx.reply(f"✅ Du hast {amount:.2f} € an {member.display_name} überwiesen (Gebühr: {fee:.2f} €).")
    await send_log(f"💸 PAY – {ctx.author} → {member}: {amount:.2f} € (Gebühr: {fee:.2f} €)")

# Admin: Geld hinzufügen
@bot.command()
async def addmoney(ctx, member: discord.Member, amount: float):
    if not is_admin(ctx):
        return await ctx.reply("❌ Nur Admins dürfen das.")
    accounts = get_account(member.id)
    accounts[str(member.id)]["balance"] += amount
    save_accounts(accounts)
    await ctx.reply(f"✅ {amount:.2f} € zu {member.display_name} hinzugefügt.")
    await send_log(f"🛠️ ADDMONEY – {ctx.author} zu {member}: {amount:.2f} €")

# Admin: Geld entfernen
@bot.command()
async def removemoney(ctx, member: discord.Member, amount: float):
    if not is_admin(ctx):
        return await ctx.reply("❌ Nur Admins dürfen das.")
    accounts = get_account(member.id)
    accounts[str(member.id)]["balance"] -= amount
    save_accounts(accounts)
    await ctx.reply(f"✅ {amount:.2f} € von {member.display_name} entfernt.")
    await send_log(f"🛠️ REMOVEMONEY – {ctx.author} von {member}: {amount:.2f} €")

# Kredit aufnehmen
@bot.command()
async def loan(ctx, amount: float):
    if amount <= 0:
        return await ctx.reply("❌ Betrag muss größer als 0 sein.")
    accounts = get_account(ctx.author.id)
    accounts[str(ctx.author.id)]["balance"] += amount
    accounts[str(ctx.author.id)]["loan"] += amount
    accounts[str(ctx.author.id)]["loan_timer"] = 0  # Timer zurücksetzen
    save_accounts(accounts)
    await ctx.reply(f"✅ Kredit von {amount:.2f} € aufgenommen.")
    await send_log(f"💳 LOAN – {ctx.author} nahm Kredit {amount:.2f} € auf")

# Mini-Loan aufnehmen
@bot.command()
async def miniloan(ctx, amount: float):
    if amount <= 0 or amount > 50:
        return await ctx.reply("❌ Mini-Loan nur bis 50€ möglich.")
    accounts = get_account(ctx.author.id)
    accounts[str(ctx.author.id)]["balance"] += amount
    accounts[str(ctx.author.id)]["loan"] += amount
    accounts[str(ctx.author.id)]["loan_timer"] = 0  # für Rückzahlung
    save_accounts(accounts)
    await ctx.reply(f"✅ Mini-Loan von {amount:.2f} € aufgenommen, Rückzahlung innerhalb einer Woche empfohlen!")
    await send_log(f"💳 MINILOAN – {ctx.author} nahm Mini-Loan {amount:.2f} € auf")

# Kredit zurückzahlen
@bot.command()
async def payloan(ctx, amount: float):
    if amount <= 0:
        return await ctx.reply("❌ Betrag muss größer als 0 sein.")
    accounts = get_account(ctx.author.id)
    loan_amount = accounts[str(ctx.author.id)]["loan"]
    if loan_amount <= 0:
        return await ctx.reply("❌ Du hast keinen Kredit offen.")
    if amount > accounts[str(ctx.author.id)]["balance"]:
        return await ctx.reply("❌ Nicht genug Geld.")
    pay_amount = min(amount, loan_amount)
    accounts[str(ctx.author.id)]["balance"] -= pay_amount
    accounts[str(ctx.author.id)]["loan"] -= pay_amount
    save_accounts(accounts)
    await ctx.reply(f"✅ {pay_amount:.2f} € zurückgezahlt. Restkredit: {accounts[str(ctx.author.id)]['loan']:.2f} €")
    await send_log(f"💳 PAYLOAN – {ctx.author} zahlte {pay_amount:.2f} €")

# Auf Sparkonto legen
@bot.command()
async def deposit(ctx, amount: float):
    if amount <= 0:
        return await ctx.reply("❌ Betrag muss größer als 0 sein.")
    accounts = get_account(ctx.author.id)
    if accounts[str(ctx.author.id)]["balance"] < amount:
        return await ctx.reply("❌ Nicht genug Geld.")
    accounts[str(ctx.author.id)]["balance"] -= amount
    accounts[str(ctx.author.id)]["savings"] += amount
    save_accounts(accounts)
    await ctx.reply(f"✅ {amount:.2f} € auf Sparkonto gelegt.")
    await send_log(f"💰 DEPOSIT – {ctx.author} legte {amount:.2f} € auf Sparkonto")

# Vom Sparkonto abheben
@bot.command()
async def withdraw(ctx, amount: float):
    if amount <= 0:
        return await ctx.reply("❌ Betrag muss größer als 0 sein.")
    accounts = get_account(ctx.author.id)
    if accounts[str(ctx.author.id)]["savings"] < amount:
        return await ctx.reply("❌ Nicht genug auf Sparkonto.")
    accounts[str(ctx.author.id)]["savings"] -= amount
    accounts[str(ctx.author.id)]["balance"] += amount
    save_accounts(accounts)
    await ctx.reply(f"✅ {amount:.2f} € vom Sparkonto abgehoben.")
    await send_log(f"💰 WITHDRAW – {ctx.author} hob {amount:.2f} € vom Sparkonto ab")

# VIP-Konto aktivieren
@bot.command()
async def vip(ctx):
    accounts = get_account(ctx.author.id)
    if accounts[str(ctx.author.id)]["vip"]:
        return await ctx.reply("✅ Du bist bereits VIP.")
    accounts[str(ctx.author.id)]["vip"] = True
    save_accounts(accounts)
    await ctx.reply("🌟 VIP-Konto aktiviert! Du bekommst jetzt Bonuszinsen.")
    await send_log(f"🌟 VIP – {ctx.author} aktivierte VIP-Konto")

# ---------------- WÖCHENTLICHE ZINSEN & MONDAY PAYOUT ---------------- #
@tasks.loop(hours=24)
async def weekly_interest():
    today = datetime.utcnow().weekday()  # Montag = 0
    if today == 0:
        accounts = load_accounts()
        log_msg = "📅 **Zinsen & Auszahlungen (Montag)**\n"
        for user_id, data in accounts.items():
            # Zinsen auf Balance
            bonus = VIP_BONUS if data.get("vip") else 0
            interest = data["balance"] * (0.05 + bonus)
            data["balance"] += interest

            # Kredit-Zinsen
            loan_interest = data["loan"] * CREDIT_INTEREST
            data["loan"] += loan_interest
            data["loan_timer"] += 1  # für Mini-Loan Fristen

            log_msg += f"- <@{user_id}>: +{interest:.2f} € Zinsen, Kredit-Zinsen: {loan_interest:.2f} €\n"

            # Mini-Loan Strafzins nach 1 Woche
            if data["loan_timer"] > 1:
                penalty = data["loan"] * 0.02  # 2% Strafzins
                data["loan"] += penalty
                log_msg += f"  ⚠️ <@{user_id}> Mini-Loan-Strafzins: {penalty:.2f} €\n"

        # Zentrale Auszahlung
        central_account = get_account(CENTRAL_ACCOUNT_ID)
        central_account[str(CENTRAL_ACCOUNT_ID)]["balance"] += MONDAY_PAYOUT
        log_msg += f"\n🏦 Zentrale Auszahlung: +{MONDAY_PAYOUT:.2f} € an zentrales Konto\n"

        save_accounts(accounts)
        save_accounts(central_account)
        await send_log(log_msg)

@weekly_interest.before_loop
async def before_loop():
    await bot.wait_until_ready()

weekly_interest.start()

# ---------------- START BOT ---------------- #
bot.run(DISCORD_TOKEN)
