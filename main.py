import asyncio
import hashlib
import logging
import re
import tomllib
from typing import NamedTuple, Tuple

import discord
import discord.ext.commands as commands
import requests
import sqlalchemy
from sqlalchemy import MetaData, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncAttrs, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import httpx
from contextlib import asynccontextmanager

# Config global logging to console and file with format "[%(asctime)s] [%(levelname)s] %(message)s"
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Create a global sqlalchemy engine and metadata object
metadata_obj = MetaData()


class Base(AsyncAttrs, DeclarativeBase):
    pass


class DiscordVerify(Base):
    def __repr__(self):
        return f"DiscordVerify(discord_id={self.discord_id}, time={self.time}, verify_key={self.verify_key})"

    __tablename__ = 'discord_verify'
    discord_id = sqlalchemy.Column(sqlalchemy.BIGINT, primary_key=True)
    time = sqlalchemy.Column(sqlalchemy.TIMESTAMP)
    verify_key = sqlalchemy.Column(sqlalchemy.CHAR(16))


class DiscordInvite(Base):
    def __repr__(self):
        return f"DiscordInvite(invite_code={self.invite_code}, time={self.time}, used_by={self.used_by})"

    __tablename__ = 'users_invitation'
    user_id = sqlalchemy.Column(sqlalchemy.INT, primary_key=True)
    time = sqlalchemy.Column(sqlalchemy.TIMESTAMP)
    used_by = sqlalchemy.Column(sqlalchemy.INT)
    invite_code = sqlalchemy.Column(sqlalchemy.VARCHAR(16))


class Users(Base):
    def __repr__(self):
        return f"Users(id={self.id}, name={self.name}, safe_name={self.safe_name}, email={self.email}, priv={self.priv}" \
               f", pw_bcrypt={self.pw_bcrypt}, country={self.country}, silence_end={self.silence_end}" \
               f", donor_end={self.donor_end}, creation_time={self.creation_time}" \
               f", latest_activity={self.latest_activity}, clan_id={self.clan_id}, clan_priv={self.clan_priv}" \
               f", preferred_mode={self.preferred_mode}, play_style={self.play_style}" \
               f", custom_badge_name={self.custom_badge_name}, custom_badge_icon={self.custom_badge_icon}" \
               f", userpage_content={self.userpage_content}, api_key={self.api_key}, clan_rank={self.clan_rank}" \
               f", available_invite={self.available_invite}, discord_id={self.discord_id})"

    __tablename__ = 'users'
    id = sqlalchemy.Column(sqlalchemy.INT, primary_key=True)
    name = sqlalchemy.Column(sqlalchemy.VARCHAR(32))
    safe_name = sqlalchemy.Column(sqlalchemy.VARCHAR(32))
    email = sqlalchemy.Column(sqlalchemy.VARCHAR(254))
    priv = sqlalchemy.Column(sqlalchemy.INT)
    pw_bcrypt = sqlalchemy.Column(sqlalchemy.VARCHAR(60))
    country = sqlalchemy.Column(sqlalchemy.CHAR(2))
    silence_end = sqlalchemy.Column(sqlalchemy.INT)
    donor_end = sqlalchemy.Column(sqlalchemy.INT)
    creation_time = sqlalchemy.Column(sqlalchemy.INT)
    latest_activity = sqlalchemy.Column(sqlalchemy.INT)
    clan_id = sqlalchemy.Column(sqlalchemy.INT)
    clan_priv = sqlalchemy.Column(sqlalchemy.INT)
    preferred_mode = sqlalchemy.Column(sqlalchemy.INT)
    play_style = sqlalchemy.Column(sqlalchemy.INT)
    custom_badge_name = sqlalchemy.Column(sqlalchemy.VARCHAR(16))
    custom_badge_icon = sqlalchemy.Column(sqlalchemy.VARCHAR(64))
    userpage_content = sqlalchemy.Column(sqlalchemy.VARCHAR(2048))
    api_key = sqlalchemy.Column(sqlalchemy.VARCHAR(32))
    clan_rank = sqlalchemy.Column(sqlalchemy.INT)
    available_invite = sqlalchemy.Column(sqlalchemy.INT)
    discord_id = sqlalchemy.Column(sqlalchemy.BIGINT)


class Config(NamedTuple):
    """
    A class to represent the general config of the bot.
    """

    def __repr__(self):
        return f"Config(bot_token={self.bot_token}, bot_prefix={self.bot_prefix}, bot_owner={self.bot_owner}, " \
               f"donor_role={self.donor_role}, moderator_role={self.moderator_role})"

    bot_token: str
    bot_prefix: str
    bot_owner: int
    donor_role: int
    moderator_role: int
    server_id: int
    api_url: str


class DatabaseConfig(NamedTuple):
    """
    A class to represent the database config of the bot.
    """

    def __repr__(self):
        return f"DatabaseConfig(host={self.host}, port={self.port}, database={self.database}, user={self.username}, " \
               f"password={self.password})"

    host: str
    port: int
    database: str
    username: str
    password: str


def embed_from_dict(embed_dict: dict) -> discord.Embed:
    """
    Function to construct a discord.Embed object from a dictionary
    :param embed_dict:
    :return:
    """
    embed = discord.Embed()
    for key, value in embed_dict.items():
        if key == "author":
            embed.set_author(**value)
        elif key == "color":
            embed.colour = value
        elif key == "description":
            embed.description = value
        elif key == "fields":
            for field in value:
                embed.add_field(**field)
        elif key == "footer":
            embed.set_footer(**value)
        elif key == "image":
            embed.set_image(**value)
        elif key == "thumbnail":
            embed.set_thumbnail(**value)
        elif key == "timestamp":
            embed.timestamp = value
        elif key == "title":
            embed.title = value
        elif key == "type":
            embed.type = value
        elif key == "url":
            embed.url = value
    return embed


def read_config():
    """
    Function to read config from toml file name .env.toml
    :return:
    """
    global config, database_config
    with open(".env.toml", "rb") as f:
        toml_dict = tomllib.load(f)
        config = Config(**toml_dict.get("general"))
        database_config = DatabaseConfig(**toml_dict.get("database"))
    logging.info("Read config from .env.toml")
    logging.debug(f"Read config: {config}")
    logging.debug(f"Read database config: {database_config}")


# Init config
read_config()

# Global variables
client: commands.Bot = commands.Bot(command_prefix=config.bot_prefix, intents=discord.Intents.all())
config: Config
database_config: DatabaseConfig
session: async_sessionmaker


# print log to console when bot is ready
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    # Set bot status
    await client.change_presence(activity=discord.Game(name="osu!"))


@client.command(pass_context=True)
async def helpme(ctx: discord.ext.commands.Context):
    """List all commands available"""
    user = ctx.author
    logging.info(f"User {user} requested help")
    await user.send(f'Welcome to the osuVNFC discord server. Here is a list of commands you can use:\n'
                    f'{config.bot_prefix}helpme - Show this message\n'
                    f'{config.bot_prefix}verify - Verify your osu! account\n'
                    f'{config.bot_prefix}invite - Generate invite code for your friends\n'
                    f'{config.bot_prefix}register - Register a new game account using your friend\'s invite code\n'
                    f'{config.bot_prefix}rename - Change your osu! username\n'
                    f'{config.bot_prefix}findme - Find your username')


@client.command(pass_context=True)
async def verify(ctx):
    """
    Create verify code for user and send it to user dm
    :param ctx:
    :return:
    """
    user = ctx.author
    logging.info(f"User {user} requested verify code")
    async with session() as conn:
        # Check if user is already verified
        db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(Users.discord_id == user.id)
        )).scalar_one_or_none()

        if db_user is not None:
            await user.send("You are already verified")
            return

        # Create a new verify code for user
        try:
            conn.add(DiscordVerify(discord_id=user.id,
                                   verify_key=hashlib.md5(
                                       str(asyncio.get_event_loop().time()).encode()).hexdigest().__str__()[:16]))
            await conn.commit()
        except IntegrityError:
            await conn.rollback()
            await user.send("You already have a verify code. Please use that one.")

        verify_code = (await conn.execute(
            sqlalchemy.select(DiscordVerify).filter(DiscordVerify.discord_id == user.id)
        )).scalar_one_or_none().verify_key
        await user.send(f"Your verify code is {verify_code}. Use !verify <verify_code> in game to verify."
                        f"\nDo not let anyone know your verify code.")


@client.command(pass_context=True)
async def invite(ctx):
    """
    Create invite code for user and send it to user dm
    :param ctx:
    :return:
    """
    user = ctx.author
    logging.info(f"User {user} requested invite code")
    SPECIAL_PERM = False
    # Check user role
    roles = user.roles
    for role in roles:
        if role.id in [int(config.donor_role), int(config.moderator_role)]:
            SPECIAL_PERM = True
            break
        if role.is_premium_subscriber():
            SPECIAL_PERM = True
            break
    async with session() as conn:
        # Check if user is already verified
        db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(Users.discord_id == user.id)
        )).scalar_one_or_none()

        if db_user is None:
            await user.send("You are not verified. Please verify yourself before getting invite code.")
            return

        if db_user.available_invite <= 0 and not SPECIAL_PERM:
            await user.send("You have no invite available.")
            return

        # Create a new invite code for user
        conn.add(DiscordInvite(user_id=db_user.id,
                               invite_code=hashlib.md5(
                                   str(asyncio.get_event_loop().time()).encode()).hexdigest().__str__()[:16]))
        await conn.commit()

        invite_code = (await conn.execute(
            sqlalchemy.select(DiscordInvite).filter(DiscordInvite.user_id == db_user.id).order_by(
                sqlalchemy.desc(DiscordInvite.time))
        )).scalars().first().invite_code

        # Update number of invite available for user
        if not SPECIAL_PERM:
            await conn.execute(
                sqlalchemy.update(Users).where(Users.id == db_user.id).values(
                    available_invite=Users.available_invite - 1)
            )

            await conn.commit()

        await user.send(f"Your invite code is {invite_code}. The code is generated and issued only once,"
                        f" and it can be used for a single account."
                        f" It's crucial to keep the code confidential and share it privately."
                        f" Cheating may lead to consequences,"
                        f" including a ban for both the person who provided the code and the person who used it.")
        logging.info(f"User {user} got invite code {invite_code}")
        if not SPECIAL_PERM:
            await user.send(f"You have {db_user.available_invite - 1} invites left.")
        else:
            await user.send(f"Thanks to your generous. You have unlimited invites.")


@client.command(pass_context=True)
async def register(ctx):
    """Register new account"""
    global client
    user = ctx.author
    logging.info(f"User {user} requested register")
    await user.send("Please enter your invite code.")
    invite_code = await client.wait_for('message', check=lambda m: m.author == user)
    async with session() as conn:
        # Check if code is valid
        db_invite = (await conn.execute(
            sqlalchemy.select(DiscordInvite).filter(DiscordInvite.invite_code == invite_code.content)
        )).scalar_one_or_none()

    if db_invite is None:
        await user.send("Invalid invite code.")
        return
    if db_invite.used_by is not None:
        await user.send("Invite code already used.")
        return

    await user.send("Please enter your username.")
    username = await client.wait_for('message', check=lambda m: m.author == user)
    async with session() as conn:
        # Check if user is already verified
        db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(Users.discord_id == user.id)
        )).scalar_one_or_none()

        if db_user is not None:
            await user.send("You are already registered")
            return

        # Check if username is already taken
        db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(func.lower(Users.name) == username.content.lower())
        )).scalar_one_or_none()

        if db_user is not None:
            await user.send("Username already taken.")
            return

    await user.send("Please enter your password.")
    password = await client.wait_for('message', check=lambda m: m.author == user)
    await user.send("Please enter your email.")
    email = await client.wait_for('message', check=lambda m: m.author == user)

    # Create a new verify code for user
    r = requests.post(f"{config.api_url}/users", data={
        "user[username]": username.content,
        "user[password]": password.content,
        "user[user_email]": email.content,
        "user[invite_code]": invite_code.content,
        "check": 0
    })
    if r.status_code != 200:
        await user.send("Something went wrong. Please try again later.")
        return
    if r.text != 'ok':
        await user.send(r.text)
        return

    await user.send(f"Your account has been created. Please use !verify to verify your account.")


@client.command(pass_context=True)
async def rename(ctx: discord.ext.commands.Context):
    """Rename user account"""
    global client
    user = ctx.author
    logging.info(f"User {user} requested rename")

    def check(username) -> bool:
        pattern = re.compile(r"^[\w \[\]-]{2,15}$")
        if not pattern.match(username):
            return False

        if "_" in username and " " in username:
            return False

        return True

    async with session() as conn:
        db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(Users.discord_id == user.id)
        )).scalar_one_or_none()

        if db_user is None:
            await user.send("You are not verified. Please verify yourself before renaming.")
            return

        await user.send("Please enter your new username.\n"
                        " + Your username must be between 2 and 15 characters long,"
                        " + and can only contain letters, numbers, spaces, dashes and underscores.\n"
                        " + You can only use either space or underscore, not both.")
        new_username = client.wait_for("message", check=lambda m: m.author == user and check(m.content))
        new_username = (await new_username).content

        # Check if user exists
        check_db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(Users.name == new_username)
        )).scalar_one_or_none()

        if check_db_user is not None:
            await user.send("Username already taken.")
            return

        # Update username
        await conn.execute(
            sqlalchemy.update(Users).where(Users.id == db_user.id).values(name=new_username)
        )
        await conn.commit()

        await user.send(f"Your username has been changed to {new_username}.")


@client.command(pass_context=True)
async def findme(ctx: discord.ext.commands.Context):
    """Find user's account"""
    user = ctx.author
    logging.info(f"User {user} requested findme")
    await user.send("Please enter your email.")
    email = await client.wait_for('message', check=lambda m: m.author == user)
    async with session() as conn:
        db_user = (await conn.execute(
            sqlalchemy.select(Users).filter(Users.email == email.content)
        )).scalar_one_or_none()

        if db_user is None:
            await user.send("No account found.")
            return

        await user.send(f"Your username is {db_user.name}")


if __name__ == "__main__":
    read_config()
    engine = create_async_engine(
        f"mysql+asyncmy://{database_config.username}:{database_config.password}@"
        f"{database_config.host}:{database_config.port}/{database_config.database}"
    )
    session = async_sessionmaker(engine, expire_on_commit=False)
    if config.bot_token == "":
        logging.error("Bot token is empty")
        exit(1)
    client.run(config.bot_token, root_logger=True)
