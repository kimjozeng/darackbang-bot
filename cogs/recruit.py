from __future__ import annotations

import re

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
    update_recruit,
    set_message_refs,
    list_open_recruits,
)


LEVEL_RAIDS = {
    1730: {
        "세르카": ["하드"],
        "종막": ["하드"],
        "4막": ["하드"],
        "지평의 성당": ["2단계"],
    },
    1750: {
        "벨가르딘": ["노말"],
        "지평의 성당": ["3단계"],
        "세르카": ["나이트메어"],
        "종막": ["하드"],
    },
    1780: {
        "벨가르딘": ["하드", "나이트메어"],
        "지평의 성당": ["3단계"],
        "세르카": ["나이트메어"],
    },
    1800: {
        "벨가르딘": ["나이트메어"],
        "지평의 성당": ["3단계"],
        "상위 숙제": ["기타"],
    },
}


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

    @discord.ui.button(label="모집 수정", emoji="✏️", style=discord.ButtonStyle.secondary, custom_id="edit")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        recruit = await get_recruit(self.recruit_id)
        if not recruit:
            return await interaction.response.send_message(
                "모집 정보를 찾지 못했어요.",
                ephemeral=True,
            )

        if interaction.user.id != recruit["creator_id"] and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "공대장 또는 관리자만 수정할 수 있어요.",
                ephemeral=True,
            )

        await interaction.response.send_modal(EditRecruitModal(recruit))

    @discord.ui.button(label="모집 마감", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        recruit = await get_recruit(self.recruit_id)
        if not recruit:
            return await interaction.response.send_message("모집 정보를 찾지 못했어요.", ephemeral=True)

        if interaction.user.id != recruit["creator_id"] and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(
                "공대장 또는 관리자만 마감할 수 있어요.",
                ephemeral=True,
            )

        await close_recruit(self.recruit_id)
        await interaction.response.send_message("모집을 마감했어요.", ephemeral=True)
        await self.refresh(interaction)


class EditRecruitModal(discord.ui.Modal):
    def __init__(self, recruit: dict):
        super().__init__(title=f"모집 수정 #{recruit['id']}")
        self.recruit_id = recruit["id"]

        self.experience = discord.ui.TextInput(
            label="숙련도",
            default=recruit["experience"],
            max_length=30,
        )
        self.item_level = discord.ui.TextInput(
            label="최소 아이템 레벨",
            default=str(recruit["min_item_level"]),
            max_length=10,
        )
        self.start_time = discord.ui.TextInput(
            label="출발 시간",
            default=recruit["start_time"],
            max_length=40,
        )
        self.party_size = discord.ui.TextInput(
            label="모집 인원",
            default=f"딜{recruit['dealer_limit']} 서폿{recruit['support_limit']}",
            placeholder="예: 딜6 서폿2",
            max_length=40,
        )
        self.memo = discord.ui.TextInput(
            label="메모",
            default=recruit.get("memo") or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=300,
        )

        self.add_item(self.experience)
        self.add_item(self.item_level)
        self.add_item(self.start_time)
        self.add_item(self.party_size)
        self.add_item(self.memo)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            min_ilvl = int(str(self.item_level).replace(",", "").strip())
        except ValueError:
            return await interaction.response.send_message(
                "아이템 레벨은 숫자로 입력해 주세요.",
                ephemeral=True,
            )

        d = re.search(r"딜\s*(\d+)", str(self.party_size))
        s = re.search(r"서폿?\s*(\d+)", str(self.party_size))
        if not d or not s:
            return await interaction.response.send_message(
                "모집 인원은 '딜6 서폿2' 형식으로 입력해 주세요.",
                ephemeral=True,
            )

        dealer_limit = int(d.group(1))
        support_limit = int(s.group(1))
        if dealer_limit < 0 or support_limit < 0 or dealer_limit + support_limit <= 0:
            return await interaction.response.send_message(
                "모집 인원을 다시 확인해 주세요.",
                ephemeral=True,
            )

        await update_recruit(
            self.recruit_id,
            experience=str(self.experience).strip(),
            min_item_level=min_ilvl,
            dealer_limit=dealer_limit,
            support_limit=support_limit,
            start_time=str(self.start_time).strip(),
            memo=str(self.memo).strip(),
        )

        recruit = await get_recruit(self.recruit_id)
        members = await list_members(self.recruit_id)
        total = len(members)
        max_total = recruit["dealer_limit"] + recruit["support_limit"]
        should_close = recruit["status"] != "open" or total >= max_total

        if should_close and recruit["status"] == "open":
            await close_recruit(self.recruit_id)
            recruit["status"] = "closed"

        await interaction.response.edit_message(
            embed=build_embed(recruit, members),
            view=RecruitView(self.recruit_id, disabled=should_close),
        )




class RecruitModal(discord.ui.Modal):
    def __init__(self, base_level: int, raid_name: str | None, fixed_difficulty: str | None = None):
        super().__init__(title=f"{base_level}+ 레이드 모집")
        self.base_level = base_level
        self.fixed_raid_name = raid_name
        self.fixed_difficulty = fixed_difficulty

        if raid_name is None:
            self.raid = discord.ui.TextInput(
                label="콘텐츠명",
                placeholder="예: 카멘, 에기르, 길드 레이드 등",
                max_length=50,
            )
            self.add_item(self.raid)
        else:
            self.raid = None

        if fixed_difficulty is None:
            self.difficulty = discord.ui.TextInput(
                label="난이도",
                placeholder="예: 노말 / 하드 / 나이트메어",
                max_length=30,
            )
        else:
            self.difficulty = None
        self.experience = discord.ui.TextInput(
            label="숙련도",
            placeholder="트라이 / 반숙 / 숙련 / 빡숙",
            max_length=30,
        )
        self.item_level = discord.ui.TextInput(
            label="최소 아이템 레벨",
            default=str(base_level),
            max_length=10,
        )
        self.extra = discord.ui.TextInput(
            label="출발시간 / 인원 / 메모",
            placeholder="예: 21:00 | 딜6 서폿2 | 숙제팟, 듣코 가능",
            style=discord.TextStyle.paragraph,
            max_length=300,
        )

        if self.difficulty is not None:
            self.add_item(self.difficulty)
        self.add_item(self.experience)
        self.add_item(self.item_level)
        self.add_item(self.extra)

    async def on_submit(self, interaction: discord.Interaction):
        raid_name = self.fixed_raid_name or str(self.raid).strip()

        parts = [p.strip() for p in str(self.extra).split("|")]
        start_time = parts[0] if parts else "미정"
        dealer_limit, support_limit = 6, 2
        memo = " | ".join(parts[2:]) if len(parts) >= 3 else (parts[1] if len(parts) == 2 else "")

        if len(parts) >= 2:
            d = re.search(r"딜\s*(\d+)", parts[1])
            s = re.search(r"서폿?\s*(\d+)", parts[1])
            if d:
                dealer_limit = int(d.group(1))
            if s:
                support_limit = int(s.group(1))

        try:
            min_ilvl = int(str(self.item_level).replace(",", "").strip())
        except ValueError:
            return await interaction.response.send_message(
                "아이템 레벨은 숫자로 입력해 주세요.",
                ephemeral=True,
            )

        if dealer_limit < 0 or support_limit < 0 or dealer_limit + support_limit <= 0:
            return await interaction.response.send_message(
                "모집 인원을 다시 확인해 주세요.",
                ephemeral=True,
            )

        recruit_id = await create_recruit(
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            creator_id=interaction.user.id,
            raid=raid_name,
            difficulty=self.fixed_difficulty or str(self.difficulty).strip(),
            experience=str(self.experience).strip(),
            min_item_level=min_ilvl,
            dealer_limit=dealer_limit,
            support_limit=support_limit,
            start_time=start_time,
            memo=memo,
        )

        recruit = await get_recruit(recruit_id)
        await interaction.response.send_message(
            embed=build_embed(recruit, []),
            view=RecruitView(recruit_id),
        )
        msg = await interaction.original_response()

        thread = None
        try:
            thread = await msg.create_thread(
                name=f"{recruit['raid']} {recruit['difficulty']} | {recruit['start_time']}"
            )
            await thread.send(
                f"공대장 <@{recruit['creator_id']}>님이 생성한 모집 스레드입니다."
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        await set_message_refs(recruit_id, msg.id, thread.id if thread else None)


class DifficultyButton(discord.ui.Button):
    def __init__(self, base_level: int, raid_name: str, difficulty: str):
        super().__init__(label=difficulty, style=discord.ButtonStyle.primary)
        self.base_level = base_level
        self.raid_name = raid_name
        self.difficulty = difficulty

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            RecruitModal(self.base_level, self.raid_name, self.difficulty)
        )


class DifficultyView(discord.ui.View):
    def __init__(self, base_level: int, raid_name: str, difficulties: list[str]):
        super().__init__(timeout=180)
        for difficulty in difficulties:
            self.add_item(DifficultyButton(base_level, raid_name, difficulty))


class RaidButton(discord.ui.Button):
    def __init__(self, base_level: int, raid_name: str | None):
        label = "기타" if raid_name is None else raid_name
        style = discord.ButtonStyle.secondary if raid_name is None else discord.ButtonStyle.primary
        super().__init__(label=label, style=style)
        self.base_level = base_level
        self.raid_name = raid_name

    async def callback(self, interaction: discord.Interaction):
        if self.raid_name is None:
            return await interaction.response.send_modal(
                RecruitModal(self.base_level, None)
            )

        difficulties = LEVEL_RAIDS[self.base_level][self.raid_name]
        if len(difficulties) == 1:
            return await interaction.response.send_modal(
                RecruitModal(self.base_level, self.raid_name, difficulties[0])
            )

        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"⚔️ {self.raid_name}",
                description="난이도를 선택해 주세요.",
            ),
            view=DifficultyView(self.base_level, self.raid_name, difficulties),
            ephemeral=True,
        )


class LevelRaidView(discord.ui.View):
    def __init__(self, base_level: int):
        super().__init__(timeout=180)
        for raid_name in LEVEL_RAIDS[base_level]:
            self.add_item(RaidButton(base_level, raid_name))
        self.add_item(RaidButton(base_level, None))


class RecruitPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def show_level(self, interaction: discord.Interaction, level: int):
        raids = "\n".join(f"• {name}" for name in LEVEL_RAIDS[level])
        embed = discord.Embed(
            title=f"🏠 다락방 {level}+ 모집",
            description=(
                f"{raids}\n• 기타\n\n"
                "원하는 콘텐츠를 눌러 모집을 작성해 주세요."
            ),
        )
        await interaction.response.send_message(
            embed=embed,
            view=LevelRaidView(level),
            ephemeral=True,
        )

    @discord.ui.button(label="1730+", style=discord.ButtonStyle.secondary, custom_id="darack:panel:1730")
    async def level_1730(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_level(interaction, 1730)

    @discord.ui.button(label="1750+", style=discord.ButtonStyle.primary, custom_id="darack:panel:1750")
    async def level_1750(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_level(interaction, 1750)

    @discord.ui.button(label="1780+", style=discord.ButtonStyle.success, custom_id="darack:panel:1780")
    async def level_1780(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_level(interaction, 1780)

    @discord.ui.button(label="1800+", style=discord.ButtonStyle.danger, custom_id="darack:panel:1800")
    async def level_1800(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_level(interaction, 1800)


class RecruitCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="모집패널",
        description="다락방 로스트아크 모집 패널을 생성합니다.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏠 다락방 로스트아크 파티 모집",
            description=(
                "아이템 레벨 구간을 선택해 주세요.\n\n"
                "1730+ / 1750+ / 1780+ / 1800+\n"
                "각 구간에는 주요 레이드와 **기타** 모집이 준비되어 있습니다."
            ),
        )
        await interaction.response.send_message(
            embed=embed,
            view=RecruitPanelView(),
        )

    async def restore_views(self):
        self.bot.add_view(RecruitPanelView())
        for recruit in await list_open_recruits():
            self.bot.add_view(RecruitView(recruit["id"]))


async def setup(bot: commands.Bot):
    cog = RecruitCog(bot)
    await bot.add_cog(cog)
    await cog.restore_views()
