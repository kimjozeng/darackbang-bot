from __future__ import annotations

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from database.db import (
    get_guild_settings,
    get_server_roles,
    save_verified_user,
    set_auth_roles,
    set_server_role,
)


class CharacterNameModal(discord.ui.Modal, title="로스트아크 캐릭터 인증"):
    character_name = discord.ui.TextInput(
        label="캐릭터명",
        placeholder="게임에서 사용하는 캐릭터명을 입력해 주세요",
        min_length=1,
        max_length=32,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message("서버 안에서 진행해 주세요.", ephemeral=True)

        name = str(self.character_name).strip()
        if not name:
            return await interaction.response.send_message("캐릭터명을 입력해 주세요.", ephemeral=True)

        server_roles = await get_server_roles(interaction.guild.id)
        if not server_roles:
            return await interaction.response.send_message(
                "아직 로아 서버 역할이 설정되지 않았어요. 서버 관리자에게 알려 주세요.",
                ephemeral=True,
            )
        if len(server_roles) > 25:
            return await interaction.response.send_message(
                "등록된 서버 역할이 25개를 넘어 선택할 수 없어요. 관리자에게 설정을 확인해 달라고 해 주세요.",
                ephemeral=True,
            )

        settings = await get_guild_settings(interaction.guild.id)
        if not settings.get("verified_role_id"):
            return await interaction.response.send_message(
                "인증 역할이 아직 설정되지 않았어요. 서버 관리자에게 알려 주세요.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            "본인이 플레이하는 로아 서버를 선택해 주세요.",
            view=ServerRoleView(name, server_roles),
            ephemeral=True,
        )


class ServerRoleSelect(discord.ui.Select):
    def __init__(self, character_name: str, server_roles: list[dict]):
        self.character_name = character_name
        options = [
            discord.SelectOption(label=row["server_name"], value=str(row["role_id"]))
            for row in server_roles[:25]
        ]
        super().__init__(
            placeholder="로아 서버 선택",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return await interaction.response.send_message("서버 안에서 다시 진행해 주세요.", ephemeral=True)

        role_id = int(self.values[0])
        server_roles = await get_server_roles(guild.id)
        selected = next((row for row in server_roles if row["role_id"] == role_id), None)
        if selected is None:
            return await interaction.response.send_message(
                "서버 역할 설정을 찾지 못했어요. 관리자에게 알려 주세요.",
                ephemeral=True,
            )

        settings = await get_guild_settings(guild.id)
        verified_role_id = settings.get("verified_role_id")
        verified_role = guild.get_role(verified_role_id) if verified_role_id else None
        server_role = guild.get_role(role_id)
        pending_role_id = settings.get("pending_role_id")
        pending_role = guild.get_role(pending_role_id) if pending_role_id else None

        if verified_role is None or server_role is None:
            return await interaction.response.send_message(
                "인증 역할 또는 서버 역할이 삭제되었어요. 관리자에게 설정을 확인해 달라고 해 주세요.",
                ephemeral=True,
            )

        remove_ids = {row["role_id"] for row in server_roles}
        remove_ids.add(verified_role.id)
        if pending_role:
            remove_ids.add(pending_role.id)

        keep_roles = [
            role for role in member.roles
            if role != guild.default_role and role.id not in remove_ids
        ]
        new_roles = [*keep_roles, server_role, verified_role]

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await member.edit(
                nick=self.character_name,
                roles=new_roles,
                reason="모코코 메이트 서버 인증",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                "닉네임이나 역할을 변경할 권한이 없어요. 봇 역할 순서를 확인해 달라고 관리자에게 알려 주세요.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.followup.send(
                "인증 처리에 실패했어요. 잠시 후 다시 시도해 주세요.",
                ephemeral=True,
            )

        await save_verified_user(guild.id, member.id, self.character_name, selected["server_name"])
        await interaction.followup.send(
            f"인증 완료! 닉네임을 **{self.character_name}**으로 설정하고 "
            f"**{selected['server_name']}** 서버 역할을 지급했어요.",
            ephemeral=True,
        )


class ServerRoleView(discord.ui.View):
    def __init__(self, character_name: str, server_roles: list[dict]):
        super().__init__(timeout=300)
        self.add_item(ServerRoleSelect(character_name, server_roles))


class VerificationPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="인증 시작하기",
        emoji="🌱",
        style=discord.ButtonStyle.success,
        custom_id="mokoko:verify:start",
    )
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CharacterNameModal())


class VerificationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="인증패널", description="현재 채널에 모코코 메이트 인증 패널을 생성합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def verification_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🌱 모코코 메이트 서버 인증",
            description=(
                "아래 버튼을 눌러 게임 캐릭터명을 입력하고, "
                "본인이 플레이하는 로아 서버를 선택해 주세요.\n"
                "확인 후 닉네임과 서버 역할이 자동으로 설정됩니다."
            ),
            color=0xA8D878,
        )
        await interaction.response.send_message(embed=embed, view=VerificationPanel())

    @app_commands.command(name="서버역할설정", description="로아 서버명과 지급할 역할을 연결합니다.")
    @app_commands.describe(server_name="예: 루페온", role="이 서버 이용자에게 지급할 역할")
    @app_commands.default_permissions(manage_guild=True)
    async def configure_server_role(
        self,
        interaction: discord.Interaction,
        server_name: str,
        role: discord.Role,
    ):
        if interaction.guild_id is None:
            return await interaction.response.send_message("서버 안에서만 사용할 수 있어요.", ephemeral=True)
        try:
            await set_server_role(interaction.guild_id, server_name.strip(), role.id)
        except aiosqlite.IntegrityError:
            return await interaction.response.send_message(
                "해당 역할이 이미 다른 서버명에 연결되어 있어요. 역할 설정을 확인해 주세요.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            f"**{server_name.strip()}** 선택 시 {role.mention} 역할을 지급하도록 설정했어요.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="인증역할설정", description="인증 완료 역할과 선택적 미인증 역할을 설정합니다.")
    @app_commands.describe(verified_role="인증 완료 시 지급할 역할", pending_role="입장 직후 지급할 미인증 역할(선택)")
    @app_commands.default_permissions(manage_guild=True)
    async def configure_auth_roles(
        self,
        interaction: discord.Interaction,
        verified_role: discord.Role,
        pending_role: discord.Role | None = None,
    ):
        if interaction.guild_id is None:
            return await interaction.response.send_message("서버 안에서만 사용할 수 있어요.", ephemeral=True)
        await set_auth_roles(
            interaction.guild_id,
            verified_role.id,
            pending_role.id if pending_role else None,
        )
        text = f"인증 완료 역할을 {verified_role.mention}로 설정했어요."
        if pending_role:
            text += f" 입장 시 {pending_role.mention} 역할을 지급하도록 설정했어요."
        await interaction.response.send_message(
            text,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await get_guild_settings(member.guild.id)
        role_id = settings.get("pending_role_id")
        pending_role = member.guild.get_role(role_id) if role_id else None
        if pending_role is None:
            return
        try:
            await member.add_roles(pending_role, reason="모코코 메이트 신규 입장")
        except discord.Forbidden:
            print(f"[모코코 메이트] 미인증 역할 지급 권한 없음: {member.id}")
        except discord.HTTPException as exc:
            print(f"[모코코 메이트] 미인증 역할 지급 실패: {member.id} / {exc}")

    def restore_views(self):
        self.bot.add_view(VerificationPanel())


async def setup(bot: commands.Bot):
    cog = VerificationCog(bot)
    await bot.add_cog(cog)
    cog.restore_views()
