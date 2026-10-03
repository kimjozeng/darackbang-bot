from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from database.db import (
    create_recruit,
    get_recruit,
    list_members,
    join_recruit,
    leave_recruit,
    close_recruit,
    set_message_refs,
    list_open_recruits,
)


def build_embed(recruit: dict, members: list[dict]) -> discord.Embed:
    dealers = [m for m in members if m["position"] == "dealer"]
    supports = [m for m in members if m["position"] == "support"]
    total = len(dealers) + len(supports)
    max_total = recruit["dealer_limit"] + recruit["support_limit"]
    closed = recruit["status"] != "open" or total >= max_total

    embed = discord.Embed(
        title=f"⚔️ {recruit['raid']} {recruit['difficulty']} 모집",
        description="모집 완료" if closed else "함께 갈 공대원을 모집합니다.",
    )
    embed.add_field(name="숙련도", value=recruit["experience"], inline=True)
    embed.add_field(name="아이템 레벨", value=f"{recruit['min_item_level']}+", inline=True)
    embed.add_field(name="출발", value=recruit["start_time"], inline=True)
    embed.add_field(name="현재 인원", value=f"{total} / {max_total}", inline=True)
    embed.add_field(name="⚔️ 딜러", value=f"{len(dealers)} / {recruit['dealer_limit']}", inline=True)
    embed.add_field(name="✨ 서폿", value=f"{len(supports)} / {recruit['support_limit']}", inline=True)
    embed.add_field(name="공대장", value=f"<@{recruit['creator_id']}>", inline=False)
    embed.add_field(name="메모", value=recruit.get("memo") or "없음", inline=False)
    embed.set_footer(text=f"모집 ID #{recruit['id']}")
    return embed


class RecruitView(discord.ui.View):
    def __init__(self, recruit_id: int, disabled: bool = False):
        super().__init__(timeout=None)
        self.recruit_id = recruit_id
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = disabled
                child.custom_id = f"darack:{recruit_id}:{child.custom_id}"

    async def refresh(self, interaction: discord.Interaction):
        recruit = await get_recruit(self.recruit_id)
        members = await list_members(self.recruit_id)
        if not recruit:
            return
        total = len(members)
        max_total = recruit["dealer_limit"] + recruit["support_limit"]
        should_close = recruit["status"] != "open" or total >= max_total
        if should_close and recruit["status"] == "open":
            await close_recruit(self.recruit_id)
            recruit["status"] = "closed"
        await interaction.message.edit(
            embed=build_embed(recruit, members),
            view=RecruitView(self.recruit_id, disabled=should_close),
        )

    async def _join(self, interaction: discord.Interaction, position: str):
        recruit = await get_recruit(self.recruit_id)
        if not recruit or recruit["status"] != "open":
            return await interaction.response.send_message("이미 마감된 모집입니다.", ephemeral=True)
        members = await list_members(self.recruit_id)
        same_pos_count = sum(1 for m in members if m["position"] == position)
        limit = recruit["dealer_limit"] if position == "dealer" else recruit["support_limit"]
        existing = next((m for m in members if m["user_id"] == interaction.user.id), None)
        if not existing and same_pos_count >= limit:
            return await interaction.response.send_message("해당 포지션 정원이 찼어요.", ephemeral=True)
        await join_recruit(self.recruit_id, interaction.user.id, position)
        await interaction.response.send_message("참여 처리했어요.", ephemeral=True)
        await self.refresh(interaction)

    @discord.ui.button(label="딜러 참여", emoji="⚔️", style=discord.ButtonStyle.primary, custom_id="dealer")
    async def dealer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join(interaction, "dealer")

    @discord.ui.button(label="서폿 참여", emoji="✨", style=discord.ButtonStyle.success, custom_id="support")
    async def support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._join(interaction, "support")

    @discord.ui.button(label="참여 취소", emoji="❌", style=discord.ButtonStyle.secondary, custom_id="leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await leave_recruit(self.recruit_id, interaction.user.id)
        await interaction.response.send_message("참여를 취소했어요.", ephemeral=True)
        await self.refresh(interaction)

    @discord.ui.button(label="모집 마감", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        recruit = await get_recruit(self.recruit_id)
        if not recruit:
            return await interaction.response.send_message("모집 정보를 찾지 못했어요.", ephemeral=True)
        if interaction.user.id != recruit["creator_id"] and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("공대장 또는 관리자만 마감할 수 있어요.", ephemeral=True)
        await close_recruit(self.recruit_id)
        await interaction.response.send_message("모집을 마감했어요.", ephemeral=True)
        await self.refresh(interaction)


class RecruitModal(discord.ui.Modal, title="다락방 레이드 모집"):
    raid = discord.ui.TextInput(label="레이드", placeholder="예: 카멘")
    difficulty = discord.ui.TextInput(label="난이도", placeholder="예: 하드")
    experience = discord.ui.TextInput(label="숙련도", placeholder="트라이 / 반숙 / 숙련 / 빡숙")
    item_level = discord.ui.TextInput(label="최소 아이템 레벨", placeholder="예: 1700")
    extra = discord.ui.TextInput(
        label="출발시간 / 인원 / 메모",
        placeholder="예: 21:00 | 딜6 서폿2 | 숙제팟, 듣코 가능",
        style=discord.TextStyle.paragraph,
    )

    async def on_submit(self, interaction: discord.Interaction):
        parts = [p.strip() for p in str(self.extra).split("|")]
        start_time = parts[0] if parts else "미정"
        dealer_limit, support_limit = 6, 2
        memo = " | ".join(parts[2:]) if len(parts) >= 3 else (parts[1] if len(parts) == 2 else "")
        if len(parts) >= 2:
            import re
            d = re.search(r"딜\s*(\d+)", parts[1])
            s = re.search(r"서폿?\s*(\d+)", parts[1])
            if d:
                dealer_limit = int(d.group(1))
            if s:
                support_limit = int(s.group(1))
        try:
            min_ilvl = int(str(self.item_level).replace(",", "").strip())
        except ValueError:
            return await interaction.response.send_message("아이템 레벨은 숫자로 입력해 주세요.", ephemeral=True)

        recruit_id = await create_recruit(
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            creator_id=interaction.user.id,
            raid=str(self.raid).strip(),
            difficulty=str(self.difficulty).strip(),
            experience=str(self.experience).strip(),
            min_item_level=min_ilvl,
            dealer_limit=dealer_limit,
            support_limit=support_limit,
            start_time=start_time,
            memo=memo,
        )
        recruit = await get_recruit(recruit_id)
        await interaction.response.send_message(
            embed=build_embed(recruit, []), view=RecruitView(recruit_id),
        )
        msg = await interaction.original_response()
        thread = None
        try:
            thread = await msg.create_thread(name=f"{recruit['raid']} {recruit['difficulty']} | {recruit['start_time']}")
            await thread.send(f"공대장 <@{recruit['creator_id']}>님이 생성한 모집 스레드입니다.")
        except (discord.Forbidden, discord.HTTPException):
            pass
        await set_message_refs(recruit_id, msg.id, thread.id if thread else None)


class RecruitPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="레이드 모집", emoji="⚔️", style=discord.ButtonStyle.primary, custom_id="darack:panel:create")
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RecruitModal())


class RecruitCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="모집패널", description="다락방 로스트아크 모집 패널을 생성합니다.")
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏠 다락방 로스트아크 파티 모집",
            description="버튼을 눌러 레이드 모집을 생성해 주세요.",
        )
        await interaction.response.send_message(embed=embed, view=RecruitPanelView())

    async def restore_views(self):
        self.bot.add_view(RecruitPanelView())
        for recruit in await list_open_recruits():
            self.bot.add_view(RecruitView(recruit["id"]))


async def setup(bot: commands.Bot):
    cog = RecruitCog(bot)
    await bot.add_cog(cog)
    await cog.restore_views()
