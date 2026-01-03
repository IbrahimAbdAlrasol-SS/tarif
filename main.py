from typing import List, Dict, Optional, Union
from datetime import datetime
import re
import time
import random
from tgram import TgBot, filters
from tgram.types import (
    InlineKeyboardButton as Button,
    InlineKeyboardMarkup as Markup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    Message,
    CallbackQuery,
    InputMediaPhoto,
)
import uuid
from kvsqlite import Client
import logging
from dataclasses import dataclass, asdict
import asyncio

# Monkeypatch tgram.filters.chat to support CallbackQuery
def patched_chat_filter(ids: Union[str, int, List[Union[str, int]]]) -> filters.Filter:
    """Filter messages coming from one or more chats (Patched for CallbackQuery)"""
    ids = (
        {ids.lower() if isinstance(ids, str) else ids}
        if not isinstance(ids, list)
        else {i.lower() if isinstance(i, str) else i for i in ids}
    )

    async def chat_filter(_, m):
        chat_obj = getattr(m, "chat", None)
        if not chat_obj and isinstance(m, CallbackQuery) and m.message:
            chat_obj = m.message.chat
            
        if not chat_obj:
            return False
            
        return chat_obj.id in ids or (chat_obj.username and chat_obj.username.lower() in ids)

    return filters.Filter(chat_filter)

filters.chat = patched_chat_filter

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 1
MAX_BIO_LENGTH = 500
MIN_BIO_LENGTH = 10

ARAB_LOCATIONS = {
    "السعودية": ["الرياض", "مكة المكرمة", "المدينة المنورة", "القصيم", "الشرقية", "عسير", "تبوك", "حائل", "الحدود الشمالية", "جازان", "نجران", "الباحة", "الجوف"],
    "مصر": ["القاهرة", "الجيزة", "الإسكندرية", "الدقهلية", "الشرقية", "المنوفية", "القليوبية", "البحيرة", "الغربية", "بور سعيد", "دمياط", "الإسماعيلية", "السويس", "كفر الشيخ", "الفيوم", "بني سويف", "المنيا", "أسيوط", "سوهاج", "قنا", "الأقصر", "أسوان", "البحر الأحمر", "الوادي الجديد", "مطروح", "شمال سيناء", "جنوب سيناء"],
    "الإمارات": ["أبو ظبي", "دبي", "الشارقة", "عجمان", "أم القيوين", "رأس الخيمة", "الفجيرة"],
    "الكويت": ["العاصمة", "الأحمدي", "الفروانية", "الجهراء", "حولي", "مبارك الكبير"],
    "قطر": ["الدوحة", "الريان", "الواكرة", "أم صلال", "الخور", "الشمال", "الظعاين", "الشيحانية"],
    "البحرين": ["العاصمة", "المحرق", "الشمالية", "الجنوبية"],
    "عمان": ["مسقط", "ظفار", "مسندم", "البريمي", "الداخلية", "شمال الباطنة", "جنوب الباطنة", "شمال الشرقية", "جنوب الشرقية", "الظاهرة", "الوسطى"],
    "الأردن": ["عمان", "إربد", "الزرقاء", "المفرق", "عجلون", "جرش", "مادبا", "البلقاء", "الكرك", "الطفيلة", "معان", "العقبة"],
    "العراق": ["بغداد", "البصرة", "نينوى", "أربيل", "النجف", "ذي قار", "كركوك", "الأنبار", "ديالى", "المثنى", "القادسية", "ميسان", "واسط", "صلاح الدين", "دهوك", "السليمانية", "بابل", "كربلاء"],
    "المغرب": ["الدار البيضاء", "الرباط", "فاس", "مراكش", "أكادير", "طنجة", "مكناس", "وجدة", "القنيطرة", "تطوان"],
    "الجزائر": ["الجزائر", "وهران", "قسنطينة", "عنابة", "البليدة", "باتنة", "الجلفة", "سطيف", "سيدي بلعباس", "ببسكرة"],
    "تونس": ["تونس", "صفاقس", "سوسة", "القيروان", "بنزرت", "قابس", "أريانة", "القصرين", "قفصة", "المنستير"],
    "ليبيا": ["طرابلس", "بنغازي", "مصراتة", "البيضاء", "الزاوية", "طبرق", "سبها", "الخمس", "درنة", "سرت"],
    "السودان": ["الخرطوم", "أم درمان", "بورتسودان", "نيالا", "كسلا", "الأبيض", "القضارف", "الفاشر", "الضعين", "الدمازين"],
    "فلسطين": ["القدس", "غزة", "رام الله", "الخليل", "نابلس", "جنين", "بيت لحم", "طولكرم", "قلقيلية", "سلفيت", "أريحا", "طوباس"],
    "لبنان": ["بيروت", "جبل لبنان", "الشمال", "الجنوب", "البقاع", "النبطية", "بعلبك الهرمل", "عكار"],
    "سوريا": ["دمشق", "حلب", "ريف دمشق", "حمص", "حماة", "اللاذقية", "إدلب", "الحسكة", "دير الزور", "طرطوس", "الرقة", "درعا", "السويداء", "القنيطرة"],
    "اليمن": ["صنعاء", "عدن", "تعز", "الحديدة", "إب", "ذمار", "حجة", "حضرموت", "عمران", "البيضاء"],
    "موريتانيا": ["نواكشوط", "نواذيبو", "روصو", "كيفه", "كيهيدي", "النعمة", "أطار", "الزويرات"],
    "الصومال": ["مقديشو", "هرجيسا", "بوصاصو", "جالكعيو", "بربرة", "مركة", "كيسمايو", "بيدوا"],
    "جيبوتي": ["جيبوتي", "علي صبيح", "تاجورة", "دخيل", "أوبوك"],
    "جزر القمر": ["موروني", "موتسامودو", "فومبوني"]
}

@dataclass
class Profile:
    id: str
    photo_id: str
    bio: str
    user_id: int
    message_id: int
    age: int
    gender: str
    location: str
    interests: str
    likes: int = 0
    dislikes: int = 0
    created_at: str = str(datetime.now())
    last_active: str = str(datetime.now())
    show_age: bool = True
    show_location: bool = True
    verified: bool = False
    target_gender: str = "كلاهما"
    target_age_range: List[int] = None
    preferred_location: str = "الكل"

    @classmethod
    def create_new(cls, photo_id: str, bio: str, user_id: int, message_id: int, age: int, gender: str, location: str, interests: str, target_gender: str):
        return cls(
            id=str(uuid.uuid4()),
            photo_id=photo_id,
            bio=bio,
            user_id=user_id,
            message_id=message_id,
            age=age,
            gender=gender,
            location=location,
            interests=interests,
            target_gender=target_gender,
            target_age_range=[18, 40]
        )

@dataclass
class PrivateMessage:
    id: str
    sender_id: int
    receiver_id: int
    content: str
    timestamp: str = str(datetime.now())
    read: bool = False

class VerificationSystem:
    def __init__(self, bot):
        self.bot = bot
        
    async def request_verification(self, user_id: int):
        await self.bot.bot.send_message(
            user_id,
            "🔐 <b>توثيق الحساب</b>\n\nللحصول على الشارة الزرقاء، يرجى إرسال صورة سيلفي لك وأنت تحمل ورقة مكتوب عليها اسمك وتاريخ اليوم.\n\nسيتم مراجعة الطلب يدوياً.",
        )
        # In a real scenario, we would set a state here to expect a photo.
        # For this implementation, we assume the next photo sent is for verification if state matches.
        # However, due to complexity, we'll just notify admins directly if they send a photo with specific caption or command.
        # Or simpler:
        
    async def verify_user(self, user_id: int):
        profile = await self.bot.get_user_profile(user_id)
        if profile:
            await self.bot.update_profile(user_id, {"verified": True})
            try:
                await self.bot.bot.send_message(user_id, "✅ تم توثيق حسابك بنجاح!")
            except:
                pass
            return True
        return False

class SecuritySystem:
    def __init__(self, bot):
        self.bot = bot
        self.suspicious_patterns = [
            r"(?i)(رقم.*هاتف|واتساب|واتس)",
            r"(?i)(سناب.*شات|سناب)",
            r"(?i)(انستا|انستغرام)",
            r"(?i)(فيسبوك|فيس)",
            r"\d{10,}",  # Long numbers
            r"@\w+",  # Mentions
        ]
        self.known_fake_photos = ["file_id_1", "file_id_2"] # Populated with hashes in real app

    async def detect_fake_profiles(self):
        data = await self.bot.db.get("data")
        profiles = data.get("profiles", [])
        fake_users = []
        
        for p in profiles:
            # Heuristic 1: Account created today + Generic Bio
            try:
                created = datetime.fromisoformat(p.get('created_at', str(datetime.now())))
                if (datetime.now() - created).days < 1 and len(p['bio']) < 15:
                    fake_users.append(p)
            except: pass
            
        return fake_users

    async def check_message_content(self, message: str, user_id: int) -> bool:
        """Check message content for sensitive info"""
        for pattern in self.suspicious_patterns:
            if re.search(pattern, message):
                # Log suspicious activity logic here
                return False
        
        offensive_words = ["كذا", "كذا"]  # Add offensive words
        for word in offensive_words:
            if word in message.lower():
                await self.bot.bot.send_message(user_id, "⚠️ محتوى غير لائق")
                return False
        
        return True
    
    async def rate_limit_user(self, user_id: int, action: str) -> bool:
        """Rate limit user actions"""
        key = f"rate_limit_{user_id}_{action}"
        current_time = time.time()
        
        limit_data = await self.bot.db.get(key)
        if not limit_data:
            limit_data = {"count": 1, "first_time": current_time}
        else:
            limit_data["count"] += 1
        
        limits = {
            "like": {"max": 50, "window": 86400},
            "message": {"max": 20, "window": 3600},
            "profile_view": {"max": 100, "window": 3600},
        }
        
        limit = limits.get(action, {"max": 10, "window": 3600})
        
        if limit_data["count"] > limit["max"]:
            if current_time - limit_data["first_time"] < limit["window"]:
                await self.bot.bot.send_message(
                    user_id,
                    f"⏳ لقد تجاوزت الحد المسموح للإجراءات. يرجى الانتظار."
                )
                return False
            else:
                 # Reset if window passed
                 limit_data = {"count": 1, "first_time": current_time}

        await self.bot.db.set(key, limit_data, ex=limit["window"])
        return True

class NotificationSystem:
    def __init__(self, bot):
        self.bot = bot
    
    async def send_notification(self, user_id: int, notification_type: str, data: dict):
        """Send smart notifications"""
        notifications = {
            "new_match": {
                "text": "✨ لديك مطابقة جديدة!",
                "keyboard": Markup([
                    [Button("👀 مشاهدة الملف", callback_data=f"view_profile:{data.get('match_id')}")],
                    [Button("💬 إرسال رسالة", callback_data=f"message:{data.get('user_id')}")]
                ])
            },
            "new_like": {
                "text": "💖 شخص ما أعجب بملفك الشخصي!",
                "keyboard": Markup([
                    [Button("👀 معرفة من؟", callback_data=f"view_profile:{data.get('liker_id')}")]
                ])
            },
            "new_message": {
                "text": f"📩 رسالة جديدة من {data.get('sender_name', 'مستخدم')}",
                "keyboard": Markup([
                    [Button("📥 فتح الرسالة", callback_data=f"open_message:{data.get('message_id')}")]
                ])
            },
            "profile_viewed": {
                "text": f"👀 {data.get('viewer_name', 'شخص')} شاهد ملفك الشخصي",
                "keyboard": Markup([
                    [Button("👀 مشاهدة ملفه", callback_data=f"view_profile:{data.get('viewer_id')}")]
                ])
            },
             "daily_reminder": {
                "text": "📅 لديك إعجابات جديدة تنتظرك اليوم!",
                "keyboard": Markup([
                    [Button("👀 تصفح الملفات", callback_data="browse:0")]
                ])
            }
        }
        
        notification = notifications.get(notification_type)
        if notification:
            try:
                await self.bot.bot.send_message(
                    user_id,
                    notification["text"],
                    reply_markup=notification.get("keyboard")
                )
            except Exception:
                pass

class AnalyticsSystem:
    def __init__(self, bot):
        self.bot = bot
    
    async def get_detailed_stats(self):
        """Detailed statistics"""
        data = await self.bot.db.get("data")
        profiles = data.get("profiles", [])
        
        # Helper to safely get date
        def get_days_since_active(p):
            try:
                last_active = datetime.fromisoformat(p.get('last_active', str(datetime.now())))
                return (datetime.now() - last_active).days
            except:
                return 0

        stats = {
            "total_users": len(profiles),
            "active_users": sum(1 for p in profiles if get_days_since_active(p) <= 7),
            "gender_distribution": {
                "male": sum(1 for p in profiles if p.get('gender') == 'ذكر'),
                "female": sum(1 for p in profiles if p.get('gender') == 'أنثى'),
                "other": sum(1 for p in profiles if p.get('gender') == 'أخرى')
            }
        }
        return stats

class UserSettings:
    def __init__(self, bot):
        self.bot = bot
    
    async def get_settings_keyboard(self, user_id: int):
        user_data = await self.bot.db.get(f"user_{user_id}") or {}
        profile_data = await self.bot.get_user_profile(user_id)
        
        if not profile_data:
            return None

        current_target = profile_data.get("target_gender", "كلاهما")
        
        buttons = [
            [
                Button(
                    f"🔔 الإشعارات: {'✅' if user_data.get('notifications', True) else '❌'}",
                    callback_data=f"toggle_setting:notifications"
                )
            ],
            [
                Button(
                    f"👀 إظهار العمر: {'✅' if profile_data.get('show_age', True) else '❌'}",
                    callback_data=f"toggle_setting:show_age"
                )
            ],
             [
                Button(
                    f"📍 إظهار الموقع: {'✅' if profile_data.get('show_location', True) else '❌'}",
                    callback_data=f"toggle_setting:show_location"
                )
            ],
            [
                Button(
                    f"🎯 من تبحث عنه: {current_target}",
                    callback_data="change_target_gender"
                )
            ],
             [Button("💾 حفظ", callback_data="save_settings")],
             [Button("🔙 رجوع", callback_data="back_to_main")]
        ]
        return Markup(buttons)

class MatchingSystem:
    def __init__(self, bot):
        self.bot = bot

    async def find_matches(self, user_id: int):
        user_profile = await self.bot.get_user_profile(user_id)
        if not user_profile:
             return []
             
        data = await self.bot.db.get("data")
        all_profiles = data.get("profiles", [])
        
        matches = []
        user_interests = set(user_profile['interests'].split())
        
        for profile in all_profiles:
            if profile['user_id'] == user_id:
                continue
            
            # 1. Gender Filtering (Strict)
            target = user_profile.get("target_gender", "كلاهما")
            if target != "كلاهما" and profile['gender'] != target:
                continue
                
            # 2. Blocked/Liked Filtering
            # (Assuming we don't show already liked profiles in matches, optional)
            
            score = 0
            
            # 3. Location Score (30 points)
            try:
                if profile['location'] == user_profile['location']:
                    score += 30
                elif profile['location'].split('-')[0] == user_profile['location'].split('-')[0]: # Same Country
                    score += 15
            except: pass

            # 4. Age Score (20 points)
            try:
                age_diff = abs(int(profile['age']) - int(user_profile['age']))
                if age_diff <= 2:
                    score += 20
                elif age_diff <= 5:
                    score += 10
            except: pass
            
            # 5. Interests Score (40 points)
            try:
                prof_interests = set(profile['interests'].split())
                common = user_interests.intersection(prof_interests)
                if common:
                    score += min(len(common) * 10, 40)
            except: pass
            
            # 6. Activity Score (10 points)
            try:
                last_active = datetime.fromisoformat(profile.get('last_active', str(datetime.now())))
                if (datetime.now() - last_active).days < 1:
                    score += 10
            except: pass

            if score > 0:
                matches.append({'profile': profile, 'score': score})
            
        return sorted(matches, key=lambda x: x['score'], reverse=True)

class PremiumSystem:
    def __init__(self, bot):
        self.bot = bot
        
    async def is_premium(self, user_id: int) -> bool:
        user_data = await self.bot.db.get(f"user_{user_id}")
        return user_data and user_data.get("is_premium", False)

    async def grant_premium(self, user_id: int, days: int = 30):
        user_data = await self.bot.db.get(f"user_{user_id}")
        if user_data:
            user_data["is_premium"] = True
            # Set expiry date logic here if needed
            await self.bot.db.set(f"user_{user_id}", user_data)

class SupportSystem:
    def __init__(self, bot):
        self.bot = bot

    async def create_ticket(self, user_id: int, content: str):
        ticket_id = str(uuid.uuid4())[:8]
        ticket = {
            "id": ticket_id,
            "user_id": user_id,
            "content": content,
            "status": "open",
            "created_at": str(datetime.now())
        }
        
        data = await self.bot.db.get("support_tickets") or []
        data.append(ticket)
        await self.bot.db.set("support_tickets", data)
        
        # Notify Admins
        for admin in self.bot.admin_ids:
            try:
                await self.bot.bot.send_message(
                    admin, 
                    f"🎫 <b>تذكرة جديدة #{ticket_id}</b>\nمن: {user_id}\n\n{content}",
                    reply_markup=Markup([[Button("رد", callback_data=f"reply_ticket:{ticket_id}")]])
                )
            except: pass
            
        return ticket_id

class AdminPanel:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.setup_admin_handlers()

    def setup_admin_handlers(self):
        self.bot.bot.on_message(
            filters.command(["admin"]) & filters.user(self.bot.admin_ids)
        )(self.admin_panel)
        self.bot.bot.on_callback_query(filters.regex("^admin:"))(
            self.handle_admin_callbacks
        )
        self.bot.bot.on_callback_query(filters.regex("^channels:"))(
            self.handle_channels
        )

    def get_admin_keyboard(self) -> Markup:
        return Markup(
            [
                [
                    Button(text="📢 إذاعة", callback_data="admin:broadcast"),
                    Button(text="📊 الاحصائيات", callback_data="admin:stats"),
                ],
                [
                     Button(text="👥 إدارة المستخدمين", callback_data="admin:users"),
                     Button(text="📺 القنوات الاجبارية", callback_data="admin:channels")
                ],
            ]
        )

    def get_channels_keyboard(self, channels: list) -> Markup:
        buttons = []
        for channel in channels:
            buttons.append(
                [
                    Button(text=f"📺 {channel}", callback_data=f"channels:view:{channel}"),
                    Button(text="❌ حذف", callback_data=f"channels:del:{channel}")
                ]
            )
        buttons.append([Button(text="➕ اضافة قناة", callback_data="channels:add")])
        buttons.append([Button(text="🔙 رجوع", callback_data="admin:back")])
        return Markup(buttons)

    async def admin_panel(self, _, message: Message) -> None:
        text = "<b>🎛 لوحة التحكم</b>\n\nاختر من القائمة ادناه:"
        await message.reply_text(text, reply_markup=self.get_admin_keyboard())

    async def admin_broadcast_action(self, query: CallbackQuery):
        text = "📢 <b>إذاعة</b>\n\nارسل او قم بتوجيه الرسالة المراد ارسالها."
        await query.message.edit_text(
            text,
            reply_markup=Markup(
                [[Button(text="🔙 رجوع", callback_data="admin:back")]]
            ),
        )
        try:
            response = await self.bot.ask(
                query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_broadcast_message(self.bot.bot, response)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {e}")

    async def admin_users_menu(self, query: CallbackQuery):
        text = "<b>👥 إدارة المستخدمين</b>\n\nاختر من القائمة:"
        await query.message.edit_text(
            text,
            reply_markup=Markup([
                [Button("⛔️ حظر مستخدم", callback_data="admin:ban_user"), Button("✅ فك حظر", callback_data="admin:unban_user")],
                [Button("ℹ️ معلومات مستخدم", callback_data="admin:user_info"), Button("🗑 حذف ملف", callback_data="admin:del_profile")],
                [Button("✅ توثيق مستخدم", callback_data="admin:verify_user")],
                [Button("🔙 رجوع", callback_data="admin:back")]
            ])
        )

    async def admin_verify_user_action(self, query: CallbackQuery):
        await query.message.edit_text("🔢 ارسل آيدي المستخدم لتوثيق حسابه:", reply_markup=Markup([[Button("🔙 رجوع", callback_data="admin:users")]]))
        try:
            response = await self.bot.ask(
                query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_verify_user(self.bot.bot, response)
        except Exception as e:
            logger.error(f"Verify user error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {str(e)}")

    async def admin_ban_user_action(self, query: CallbackQuery):
        await query.message.edit_text("🔢 ارسل آيدي المستخدم لحظره:", reply_markup=Markup([[Button("🔙 رجوع", callback_data="admin:users")]]))
        try:
            response = await self.bot.ask(
                query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_ban_user(self.bot.bot, response)
        except Exception as e:
            logger.error(f"Ban user error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {str(e)}")

    async def admin_unban_user_action(self, query: CallbackQuery):
        await query.message.edit_text("🔢 ارسل آيدي المستخدم لفك حظره:", reply_markup=Markup([[Button("🔙 رجوع", callback_data="admin:users")]]))
        try:
            response = await self.bot.ask(
                query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_unban_user(self.bot.bot, response)
        except Exception as e:
            logger.error(f"Unban user error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {str(e)}")

    async def admin_user_info_action(self, query: CallbackQuery):
        await query.message.edit_text("🔢 ارسل آيدي المستخدم لجلب معلوماته:", reply_markup=Markup([[Button("🔙 رجوع", callback_data="admin:users")]]))
        try:
            response = await self.bot.ask(
                chat_id=query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_get_user_info(self.bot.bot, response)
        except Exception as e:
            logger.error(f"User info error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {str(e)}")

    async def admin_del_profile_action(self, query: CallbackQuery):
        await query.message.edit_text("🔢 ارسل آيدي المستخدم لحذف ملفه الشخصي:", reply_markup=Markup([[Button("🔙 رجوع", callback_data="admin:users")]]))
        try:
            response = await self.bot.ask(
                chat_id=query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_admin_delete_profile(self.bot.bot, response)
        except Exception as e:
            logger.error(f"Del profile error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {str(e)}")

    async def admin_channels_action(self, query: CallbackQuery):
        data = await self.bot.db.get("data")
        channels = data.get("force_channels", [])
        text = "<b>📺 القنوات الاجبارية</b>\n\n"
        if channels:
            for channel in channels:
                try:
                    chat = await self.bot.bot.get_chat(channel)
                    text += f"• {chat.title} ({channel})\n"
                except Exception:
                    text += f"• {channel}\n"
        else:
            text += "لا توجد قنوات مضافة."

        await query.message.edit_text(
            text, reply_markup=self.get_channels_keyboard(channels)
        )

    async def admin_main_menu_action(self, query: CallbackQuery):
        text = "<b>🎛 لوحة التحكم</b>\n\nاختر من القائمة ادناه:"
        await query.message.edit_text(text, reply_markup=self.get_admin_keyboard())

    async def handle_admin_callbacks(self, _, query: CallbackQuery) -> None:
        if not self.bot.is_admin(query.from_user.id):
            return await query.answer("⛔️ غير مصرح لك", show_alert=True)

        action = query.data.split(":")[1]
        
        action_map = {
            "broadcast": self.admin_broadcast_action,
            "users": self.admin_users_menu,
            "verify_user": self.admin_verify_user_action,
            "ban_user": self.admin_ban_user_action,
            "unban_user": self.admin_unban_user_action,
            "user_info": self.admin_user_info_action,
            "del_profile": self.admin_del_profile_action,
            "channels": self.admin_channels_action,
            "stats": self.show_statistics,
            "back": self.admin_main_menu_action
        }

        handler = action_map.get(action)
        if handler:
            try:
                await handler(query)
            except Exception as e:
                logger.error(f"Error in admin action {action}: {e}")
                await query.answer("❌ حدث خطأ", show_alert=True)
        else:
            await query.answer("⚠️ أمر غير معروف", show_alert=True)

    async def handle_broadcast_message(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_broadcast_message called with None message")
            return
        try:
            users = [
                (await self.bot.db.get(user_key[0]))["id"]
                for user_key in await self.bot.db.keys("user_%")
            ]
            if not users:
                return await message.reply_text("❌ لا يوجد مستخدمين")

            status_msg = await message.reply_text("🚀 جاري الارسال...")
            successful = 0
            failed = 0

            for user_id in users:
                try:
                    await self.bot.bot.copy_message(
                        chat_id=user_id,
                        from_chat_id=message.chat.id,
                        message_id=message.id,
                    )
                    successful += 1
                except:
                    failed += 1

            await status_msg.edit_text(
                f"✅ تم اكتمال الارسال!\n\n"
                f"📊 الاحصائيات:\n"
                f"- عدد المستخدمين: {len(users)}\n"
                f"- تم الارسال: {successful}\n"
                f"- فشل الارسال: {failed}"
            )
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ اثناء الارسال: {str(e)}")

    async def handle_add_channel(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_add_channel called with None message")
            return
        try:
            channel_id = message.text.strip()
            if message.forward_origin:
                channel_id = message.forward_origin.chat.id
            
            db_data = await self.bot.db.get("data")
            if not db_data.get("force_channels"):
                db_data["force_channels"] = []

            if channel_id not in db_data["force_channels"]:
                db_data["force_channels"].append(channel_id)
                await self.bot.db.set("data", db_data)
                await message.reply_text("✅ تم اضافة القناة!")
            else:
                await message.reply_text("❌ القناة موجوده مسبقاً")

        except Exception as e:
            await message.reply_text(f"❌ Error adding channel: {str(e)}")

    async def handle_ban_user(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_ban_user called with None message")
            return
        try:
            user_id = int(message.text.strip())
            user_data = await self.bot.db.get(f"user_{user_id}")
            if not user_data:
                return await message.reply_text("❌ المستخدم غير موجود")
            
            user_data["banned"] = True
            await self.bot.db.set(f"user_{user_id}", user_data)
            await message.reply_text(f"⛔️ تم حظر المستخدم {user_id} بنجاح!")
        except ValueError:
            await message.reply_text("❌ الرجاء ارسال آيدي صحيح (أرقام فقط).")

    async def handle_unban_user(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_unban_user called with None message")
            return
        try:
            user_id = int(message.text.strip())
            user_data = await self.bot.db.get(f"user_{user_id}")
            if not user_data:
                return await message.reply_text("❌ المستخدم غير موجود")
            
            user_data["banned"] = False
            await self.bot.db.set(f"user_{user_id}", user_data)
            await message.reply_text(f"✅ تم فك حظر المستخدم {user_id} بنجاح!")
        except ValueError:
             await message.reply_text("❌ الرجاء ارسال آيدي صحيح.")

    async def handle_get_user_info(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_get_user_info called with None message")
            return
        try:
            user_id = int(message.text.strip())
            user_data = await self.bot.db.get(f"user_{user_id}")
            if not user_data:
                 return await message.reply_text("❌ المستخدم غير موجود")
            
            profile = await self.bot.get_user_profile(user_id)
            info = f"<b>ℹ️ معلومات المستخدم {user_id}:</b>\n\n"
            info += f"🚫 محظور: {'نعم' if user_data.get('banned') else 'لا'}\n"
            info += f"❤️ الإعجابات: {len(user_data.get('likes', []))}\n"
            info += f"⭐️ المفضلة: {len(user_data.get('favorites', []))}\n"
            
            if profile:
                info += f"\n<b>📝 الملف الشخصي:</b>\n"
                info += f"☑️ موثوق: {'نعم' if profile.get('verified') else 'لا'}\n"
                info += f"الاسم/المعرف: {profile.get('name', 'غير متوفر')}\n"
                info += f"العمر: {profile.get('age')}\n"
                info += f"الجنس: {profile.get('gender')}\n"
                info += f"الموقع: {profile.get('location')}\n"
            else:
                info += "\n❌ لا يوجد ملف شخصي."
                
            await message.reply_text(info)
        except ValueError:
            await message.reply_text("❌ الرجاء ارسال آيدي صحيح.")

    async def handle_admin_delete_profile(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_admin_delete_profile called with None message")
            return
        try:
            user_id = int(message.text.strip())
            data = await self.bot.db.get("data")
            idx = next((i for i, p in enumerate(data.get("profiles", [])) if p["user_id"] == user_id), -1)
            
            if idx != -1:
                data["profiles"].pop(idx)
                await self.bot.db.set("data", data)
                await message.reply_text(f"🗑 تم حذف ملف المستخدم {user_id} بنجاح!")
            else:
                await message.reply_text("❌ هذا المستخدم ليس لديه ملف شخصي.")
        except ValueError:
            await message.reply_text("❌ الرجاء ارسال آيدي صحيح.")

    async def handle_verify_user(self, _, message: Message, data: dict = None) -> None:
        if not message:
            logger.error("handle_verify_user called with None message")
            return
        try:
            user_id = int(message.text.strip())
            success = await self.bot.verification.verify_user(user_id)
            if success:
                await message.reply_text(f"✅ تم توثيق المستخدم {user_id} بنجاح!")
            else:
                await message.reply_text("❌ المستخدم ليس لديه ملف شخصي.")
        except ValueError:
             await message.reply_text("❌ الرجاء ارسال آيدي صحيح.")
        except Exception as e:
            await message.reply_text(f"❌ حدث خطأ: {str(e)}")


    async def admin_add_channel_action(self, query: CallbackQuery):
        text = "📺 <b>اضافة قناة</b>\n\nقم بتوجيه رسالة من القناة أو أرسل المعرف."
        await query.message.edit_text(
            text,
            reply_markup=Markup([[Button(text="🔙 رجوع", callback_data="admin:channels")]]),
        )
        try:
            response = await self.bot.ask(
                chat_id=query.message.chat.id,
                filters=filters.user(query.from_user.id)
            )
            await self.handle_add_channel(self.bot.bot, response)
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            await query.message.reply_text(f"❌ الغاء العملية: {str(e)}")

    async def admin_del_channel_action(self, query: CallbackQuery):
        try:
            channel_id = int(query.data.split(":")[2])
            data = await self.bot.db.get("data")
            if channel_id in data.get("force_channels", []):
                data["force_channels"].remove(channel_id)
                await self.bot.db.set("data", data)
                await query.answer("✅ تم حذف القناة بنجاح!")
                
                # Refresh list
                await self.admin_channels_action(query)
            else:
                await query.answer("❌ لم يتم العثور على القناة!", show_alert=True)
        except Exception as e:
            logger.error(f"Del channel error: {e}")
            await query.answer(f"❌ حدث خطأ: {str(e)}", show_alert=True)

    async def admin_view_channel_action(self, query: CallbackQuery):
        channel_id = query.data.split(":")[2]
        await query.answer(f"Channel ID: {channel_id}", show_alert=True)

    async def handle_channels(self, _, query: CallbackQuery) -> None:
        if not self.bot.is_admin(query.from_user.id):
            return await query.answer("⛔️ غير مصرح لك", show_alert=True)

        parts = query.data.split(":")
        action = parts[1]
        
        action_map = {
            "add": self.admin_add_channel_action,
            "del": self.admin_del_channel_action,
            "view": self.admin_view_channel_action
        }
        
        handler = action_map.get(action)
        if handler:
            try:
                await handler(query)
            except Exception as e:
                logger.error(f"Error in channels action {action}: {e}")
                await query.answer("❌ حدث خطأ", show_alert=True)
        else:
             await query.answer("⚠️ أمر غير معروف", show_alert=True)

    async def show_statistics(self, query: CallbackQuery) -> None:
        try:
            stats_data = await self.bot.analytics.get_detailed_stats()
            
            stats = f"""
<b>📊 احصائيات البوت المفصلة</b>

👥 <b>المستخدمين:</b>
- الإجمالي: {stats_data['total_users']}
- النشطين (آخر 7 أيام): {stats_data['active_users']}

⚧ توزيع الجنس:
- 👨 ذكور: {stats_data['gender_distribution']['male']}
- 👩 إناث: {stats_data['gender_distribution']['female']}
- ⚪️ أخرى: {stats_data['gender_distribution']['other']}

"""
            await query.message.edit_text(
                stats,
                reply_markup=Markup(
                    [
                        [
                            Button(text="🔄 تحديث", callback_data="admin:stats"),
                            Button(text="🔙 رجوع", callback_data="admin:back"),
                        ]
                    ]
                ),
            )
        except Exception as e:
            await query.message.edit_text(f"❌ حدث خطأ: {str(e)}")

class AchievementSystem:
    def __init__(self, bot):
        self.bot = bot
        self.achievements = {
            "first_match": "🎉 أول مطابقة!",
            "popular": "🌟 مشهور (100 إعجاب)",
            "verified": "☑️ موثوق"
        }
    async def check_achievements(self, user_id: int):
        profile = await self.bot.get_user_profile(user_id)
        if not profile: return
        user_achievements = [] # Should be stored in user_data
        if profile.get("likes", 0) >= 100:
            user_achievements.append("popular")
        if profile.get("verified"):
            user_achievements.append("verified")
        # Store logic here...ذذذذذذذذذذذذذذذذذذذذذذذذذذذذذذذ
class DatingBot:
    def __init__(self, token: str, admin_ids: List[int]):
        self.bot = TgBot(token, parse_mode="HTML")
        self.db = Client("dating_bot.db")
        self.admin_ids = admin_ids
        
        # Initialize Systems
        self.security = SecuritySystem(self)
        self.notifications = NotificationSystem(self)
        self.analytics = AnalyticsSystem(self)
        self.settings = UserSettings(self)
        self.matching = MatchingSystem(self)
        self.premium = PremiumSystem(self)
        self.support = SupportSystem(self)
        self.verification = VerificationSystem(self)
        self.achievements = AchievementSystem(self)
        
        self.setup_handlers()
        self.admin_panel = AdminPanel(self)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def setup_handlers(self):
        self.bot.on_message(filters.command(["start"]))(self.start_command)

        self.bot.on_callback_query(filters.regex("^explore:"))(self.explore_profiles)
        self.bot.on_callback_query(filters.regex("^create_profile:"))(self.start_create_profile)
        self.bot.on_callback_query(filters.regex("^react:"))(self.handle_reaction)
        self.bot.on_callback_query(filters.regex("^favorite:"))(self.handle_favorite)
        self.bot.on_callback_query(filters.regex("^favorites:"))(self.view_favorites)
        self.bot.on_callback_query(filters.regex("^delete_favorite:"))(self.delete_favorite)
        self.bot.on_callback_query(filters.regex("^delete_profile:"))(self.delete_profile)
        self.bot.on_callback_query(filters.regex("^start:"))(self.back_to_home)
        self.bot.on_callback_query(filters.regex("^(approve|decline):"))(self.moderate_profile)
        self.bot.on_callback_query(filters.regex("^message:"))(self.handle_message_click)
        self.bot.on_callback_query(filters.regex("^inbox:"))(self.view_inbox)
        
        # New Handlers
        self.bot.on_callback_query(filters.regex("^matches:"))(self.handle_matches)
        self.bot.on_callback_query(filters.regex("^view_profile:"))(self.handle_view_profile)
        self.bot.on_callback_query(filters.regex("^settings:"))(self.handle_settings)
        self.bot.on_callback_query(filters.regex("^toggle_setting:"))(self.handle_toggle_setting)
        self.bot.on_callback_query(filters.regex("^save_settings"))(self.handle_save_settings)
        self.bot.on_callback_query(filters.regex("^change_target_gender"))(self.handle_change_target_gender)
        self.bot.on_callback_query(filters.regex("^set_target_gender:"))(self.handle_set_target_gender)
        self.bot.on_callback_query(filters.regex("^back_to_main"))(self.back_to_home)

    async def ask(self, chat_id: int, filters=None, timeout=60) -> Optional[Message]:
        future = asyncio.get_running_loop().create_future()

        async def callback(bot, update, data):
            if not future.done():
                future.set_result(update)

        await self.bot.ask(
            next_step=callback,
            filters=filters
        )
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def init_user(self, user_id: int) -> None:
        if not await self.db.get(f"user_{user_id}"):
            await self.db.set(
                f"user_{user_id}",
                {
                    "id": user_id,
                    "likes": [],
                    "favorites": [],
                    "banned": False,
                    "messages": []
                },
            )

    async def is_banned(self, user_id: int) -> bool:
        user_data = await self.db.get(f"user_{user_id}")
        return user_data and user_data.get("banned", False)

    async def init_data(self) -> None:
        data = await self.db.get("data")
        if not data:
            data = {}
        
        updated = False
        if "profiles" not in data: 
            data["profiles"] = []
            updated = True
        if "pending_approves" not in data: 
            data["pending_approves"] = []
            updated = True
        if "force_channels" not in data: 
            data["force_channels"] = []
            updated = True
            
        if updated:
            await self.db.set("data", data)

    async def check_force_sub(self, user_id: int) -> bool:
        if self.is_admin(user_id):
            return True

        data = await self.db.get('data')
        force_channels = data.get('force_channels', [])
        if not force_channels: return True
        
        for channel in force_channels:
            try:
                member = await self.bot.get_chat_member(int(channel), int(user_id))
                if member.status in ['left', 'kicked', 'restricted']:
                    return False
            except Exception:
                continue
        return True

    async def get_user_profile(self, user_id: int) -> Optional[dict]:
        data = await self.db.get("data")
        return next((p for p in data.get("profiles", []) if p["user_id"] == user_id), None)

    async def update_profile(self, user_id: int, updates: dict) -> None:
        data = await self.db.get("data")
        for i, p in enumerate(data.get("profiles", [])):
            if p["user_id"] == user_id:
                data["profiles"][i].update(updates)
                await self.db.set("data", data)
                return

    def get_main_keyboard(self, user_id: int) -> Markup:
        return Markup(
            [
                [Button(text="👤 تصفح الملفات الشخصية", callback_data=f"explore:{user_id}:0")],
                [Button(text="💘 المطابقات الذكية", callback_data=f"matches:{user_id}")],
                [
                    Button(text="📝 إنشاء/تعديل الملف الشخصي", callback_data=f"create_profile:{user_id}"),
                    Button(text="⭐️ المفضلة", callback_data=f"favorites:{user_id}"),
                ],
                [Button(text="💬 الرسائل", callback_data=f"inbox:{user_id}")],
                [Button(text="⚙️ الإعدادات", callback_data=f"settings:{user_id}")],
            ]
        )

    async def start_command(self, _, message: Message) -> None:
        try:
            user_id = message.from_user.id
            if await self.is_banned(user_id):
                 return await message.reply_text("⛔️ عذراً، لقد تم حظرك من استخدام البوت.")

            await self.init_user(user_id)
            await self.init_data()
            
            if not await self.check_force_sub(user_id):
                data = await self.db.get('data')
                channels_text = ""
                for channel in data.get('force_channels', []):
                    try:
                        link = await self.bot.export_chat_invite_link(int(channel))
                        channels_text += f"• <b><a href='{link}'>إضغط هنا</a></b>\n"
                    except: pass
                
                return await message.reply_text(
                    f"⚠️ يجب عليك الأشتراك بالقنوات:\n\n{channels_text}\nبعد الأشتراك ارسل /start."
                )
            
            welcome_text = "<b>👋 مرحباً بك في بوت التعارف!\n\nيمكنك:\n• إنشاء ملف شخصي 📝\n• تصفح الملفات الشخصية 👤\n• التواصل مع الآخرين 💬\n\nاختر من القائمة أدناه:</b>"
            await message.reply_text(welcome_text, reply_markup=self.get_main_keyboard(user_id))
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await self.send_error_message(message.chat.id)

    async def back_to_home(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        if await self.is_banned(user_id):
             return await query.answer("⛔️ لقد تم حظرك", show_alert=True)
        try:
            await query.message.delete()
        except Exception:
            pass
        
        await self.bot.send_message(
            query.message.chat.id,
            "<b>👋 مرحباً بك في بوت التعارف!</b>\n\nاختر من القائمة أدناه:",
            reply_markup=self.get_main_keyboard(user_id)
        )

    # --- Profile Creation Flow ---
    async def start_create_profile(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        chat_id = query.message.chat.id
        
        data = await self.db.get("data")
        
        # Check pending
        if any(p['user_id'] == user_id for p in data.get("pending_approves", [])):
             return await query.answer("⚠️ لديك ملف قيد المراجعة حالياً! انتظر الموافقة.", show_alert=True)

        # Check existing
        has_profile = any(p['user_id'] == user_id for p in data.get("profiles", []))
        
        intro_text = "<b>📸 أولاً: قم بإرسال صورتك الشخصية</b>"
        if has_profile:
             intro_text = "<b>📝 تعديل الملف الشخصي</b>\nسيتم تحديث ملفك الحالي بعد المراجعة.\n\n" + intro_text

        # Initial message
        await query.message.edit_text(intro_text)
        
        try:
            # Step 1: Photo
            photo_msg = await self.bot.ask(
                chat_id=chat_id,
                filters=filters.photo & filters.user(user_id)
            )
            photo_id = photo_msg.photo[-1].file_id

            # Step 2: Age
            await self.bot.send_message(chat_id, "<b>🎂 كم عمرك؟ (أرقام فقط)</b>")
            while True:
                age_msg = await self.bot.ask(
                    chat_id=chat_id,
                    filters=filters.text & filters.user(user_id)
                )
                if age_msg.text.isdigit():
                    age = int(age_msg.text)
                    break
                await age_msg.reply_text("❌ الرجاء إدخال رقم صحيح للعمر.")

            # Step 3: Gender
            gender_markup = Markup([
                [Button("ذكر 👨", callback_data="gender:male"), Button("أنثى 👩", callback_data="gender:female")]
            ])
            
            # Send initial message for Gender
            msg = await self.bot.send_message(chat_id, "<b>⚧ ما هو جنسك؟</b>", reply_markup=gender_markup)
            
            gender_query = await self.bot.ask(
                chat_id=chat_id,
                update_type="callback_query",
                filters=filters.regex(r"^gender:") & filters.user(user_id)
            )
            gender = "ذكر" if "male" in gender_query.data else "أنثى"
            await gender_query.answer()

            # Step 3.5: Target Gender
            target_gender_markup = Markup([
                [Button("رجال 👨", callback_data="target:ذكر"), Button("نساء 👩", callback_data="target:أنثى")],
                [Button("كلاهما 👫", callback_data="target:كلاهما")]
            ])
            await self.bot.send_message(chat_id, "<b>🎯 من تبحث عنه؟</b>", reply_markup=target_gender_markup)
            
            target_query = await self.bot.ask(
                chat_id=chat_id,
                update_type="callback_query",
                filters=filters.regex(r"^target:") & filters.user(user_id)
            )
            target_gender = target_query.data.split(":")[1]
            await target_query.answer()

            # Step 4: Location (Country then Governorate)
            # 4.1 Country
            countries = list(ARAB_LOCATIONS.keys())
            # Create chunks of 3 for rows
            country_buttons = [countries[i:i + 3] for i in range(0, len(countries), 3)]
            kb_countries = Markup([
                [Button(c, callback_data=f"country:{c}") for c in row] 
                for row in country_buttons
            ])
            
            # Edit the SAME message to show Country selection
            await gender_query.message.edit_text(f"<b>✅ تم اختيار: {gender}</b>\n\n<b>🌍 اختر دولتك:</b>", reply_markup=kb_countries)
            
            country_query = await self.bot.ask(
                chat_id=chat_id,
                update_type="callback_query",
                filters=filters.regex(r"^country:") & filters.user(user_id)
            )
            country = country_query.data.split(":")[1]
            await country_query.answer()
            
            # 4.2 Governorate
            governorates = ARAB_LOCATIONS.get(country, [])
            if governorates:
                gov_buttons = [governorates[i:i + 3] for i in range(0, len(governorates), 3)]
                kb_govs = Markup([
                    [Button(g, callback_data=f"gov:{g}") for g in row] 
                    for row in gov_buttons
                ])
                # Edit the SAME message to show Governorate selection
                await country_query.message.edit_text(f"<b>✅ الدولة: {country}</b>\n\n<b>🏙 اختر المحافظة/المدينة:</b>", reply_markup=kb_govs)
                
                gov_query = await self.bot.ask(
                    chat_id=chat_id,
                    update_type="callback_query",
                    filters=filters.regex(r"^gov:") & filters.user(user_id)
                )
                gov = gov_query.data.split(":")[1]
                await gov_query.answer()
                location = f"{country} - {gov}"
                await gov_query.message.edit_text(f"<b>✅ الموقع: {location}</b>")
            else:
                location = country
                await country_query.message.edit_text(f"<b>✅ الموقع: {location}</b>")

            # Step 5: Interests
            await self.bot.send_message(chat_id, "<b>🎨 ما هي اهتماماتك؟</b>")
            interests_msg = await self.bot.ask(
                chat_id=chat_id,
                filters=filters.text & filters.user(user_id)
            )
            interests = interests_msg.text

            # Step 6: Bio
            await self.bot.send_message(chat_id, f"<b>📝 اكتب نبذة تعريفية عنك (Bio):</b>\n(بين {MIN_BIO_LENGTH} و {MAX_BIO_LENGTH} حرف)")
            while True:
                bio_msg = await self.bot.ask(
                chat_id=chat_id,
                filters=filters.text & filters.user(user_id)
            )
                if MIN_BIO_LENGTH <= len(bio_msg.text) <= MAX_BIO_LENGTH:
                    bio = bio_msg.text
                    break
                await bio_msg.reply_text(f"❌ يجب أن يكون طول النبذة بين {MIN_BIO_LENGTH} و {MAX_BIO_LENGTH} حرف.")

            # Finalize
            new_profile = Profile.create_new(
                photo_id=photo_id,
                bio=bio,
                user_id=user_id,
                message_id=0,
                age=age,
                gender=gender,
                location=location,
                interests=interests,
                target_gender=target_gender
            )
            
            db_data = await self.db.get("data")
            db_data["pending_approves"].append(asdict(new_profile))
            await self.db.set("data", db_data)

            # Notify Admins
            for admin in self.admin_ids:
                kb = Markup([[Button("✅ قبول", callback_data=f"approve:{new_profile.id}"), Button("❌ رفض", callback_data=f"decline:{new_profile.id}")]])
                caption = f"<b>👤 ملف جديد للمراجعة</b>\n\nالاسم/المعرف: {user_id}\nالعمر: {new_profile.age}\nالجنس: {new_profile.gender}\nالموقع: {new_profile.location}\nالاهتمامات: {new_profile.interests}\nالنبذة: {new_profile.bio}"
                try:
                    await self.bot.send_photo(chat_id=admin, photo=new_profile.photo_id, caption=caption, reply_markup=kb)
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin}: {e}")

            await self.bot.send_message(chat_id, "✅ تم إرسال ملفك للمراجعة! سيتم إخطارك عند الموافقة.")

        except TimeoutError:
             await self.bot.send_message(chat_id, "❌ انتهت مهلة التسجيل. حاول مرة أخرى.")
        except Exception as e:
             logger.exception(e)
             await self.bot.send_message(chat_id, "❌ حدث خطأ أثناء التسجيل.")

    # --- Moderation ---
    async def moderate_profile(self, _, query: CallbackQuery) -> None:
        if query.from_user.id not in self.admin_ids: return
        action, profile_id = query.data.split(":")
        data = await self.db.get("data")
        
        # Find profile in pending
        idx = next((i for i, p in enumerate(data["pending_approves"]) if p["id"] == profile_id), -1)
        if idx == -1: return await query.answer("❌ الملف غير موجود", show_alert=True)
        
        profile = data["pending_approves"][idx]
        
        if action == "approve":
            # Remove existing profile for this user if exists (Update Mode)
            data["profiles"] = [p for p in data["profiles"] if p["user_id"] != profile["user_id"]]
            
            data["profiles"].append(profile)
            await self.bot.send_message(profile["user_id"], "🎉 تمت الموافقة على ملفك الشخصي!")
        else:
            await self.bot.send_message(profile["user_id"], "❌ تم رفض ملفك الشخصي.")

        data["pending_approves"].pop(idx)
        await self.db.set("data", data)
        await query.message.delete()

    # --- Exploration ---
    async def explore_profiles(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        if not await self.check_force_sub(user_id):
            return await query.answer("⚠️ اشترك في القنوات أولاً", show_alert=True)

        try:
            parts = query.data.split(":")
            # Format: explore:user_id:page
            page = int(parts[2])
        except:
            page = 0

        data = await self.db.get("data")
        all_profiles = data.get("profiles", [])
        
        # Apply Filters
        user_profile = await self.get_user_profile(user_id)
        filtered_profiles = all_profiles
        if user_profile:
             target = user_profile.get("target_gender", "كلاهما")
             if target != "كلاهما":
                 filtered_profiles = [p for p in all_profiles if p.get("gender") == target]
        
        if not filtered_profiles:
            return await query.answer("📭 لا توجد ملفات تطابق بحثك!", show_alert=True)

        if page >= len(filtered_profiles): page = 0
        if page < 0: page = len(filtered_profiles) - 1
        
        profile = filtered_profiles[page]
        
        # Privacy Check
        age_display = profile['age'] if profile.get('show_age', True) else "🔒"
        location_display = profile['location'] if profile.get('show_location', True) else "🔒"
        verified_badge = "☑️" if profile.get('verified') else ""
        
        caption = f"""
<b>👤 الملف الشخصي {verified_badge}</b>

<b>🎂 العمر:</b> {age_display}
<b>⚧ الجنس:</b> {profile['gender']}
<b>📍 الموقع:</b> {location_display}
<b>🎨 الاهتمامات:</b> {profile['interests']}

<b>📝 نبذة:</b>
{profile['bio']}

❤️ {profile['likes']} | 👎 {profile['dislikes']}
"""
        buttons = []
        # Navigation
        nav = []
        if len(filtered_profiles) > 1:
            nav.append(Button("⬅️", callback_data=f"explore:{user_id}:{page-1}"))
            nav.append(Button(f"{page+1}/{len(filtered_profiles)}", callback_data="noop"))
            nav.append(Button("➡️", callback_data=f"explore:{user_id}:{page+1}"))
        buttons.append(nav)
        
        # Actions
        actions = [
            Button("💖 إعجاب", callback_data=f"react:like:{page}:{profile['id']}"),
            Button("💌 رسالة", callback_data=f"message:{profile['user_id']}"),
            Button("⭐️ حفظ", callback_data=f"favorite:{page}:{profile['id']}")
        ]
        buttons.append(actions)
        
        if profile['user_id'] == user_id:
             buttons.append([Button("🗑 حذف ملفي", callback_data=f"delete_profile:{page}:{profile['id']}")])
        
        buttons.append([Button("🏠 القائمة الرئيسية", callback_data=f"start:{user_id}")])

        try:
            await query.message.edit_media(
                media=InputMediaPhoto(profile['photo_id'], caption=caption),
                reply_markup=Markup(buttons)
            )
        except Exception:
            await query.message.delete()
            await self.bot.send_photo(query.message.chat.id, profile['photo_id'], caption=caption, reply_markup=Markup(buttons))

    # --- Reactions & Favorites ---
    async def handle_reaction(self, _, query: CallbackQuery) -> None:
        _, type, page, pid = query.data.split(":")
        user_id = query.from_user.id
        data = await self.db.get("data")
        user_data = await self.db.get(f"user_{user_id}")
        
        profile = next((p for p in data["profiles"] if p["id"] == pid), None)
        if not profile: return await query.answer("❌ الملف غير موجود", show_alert=True)
        
        if pid in user_data["likes"]:
            return await query.answer("لقد أعجبت بهذا الملف مسبقاً", show_alert=True)
            
        user_data["likes"].append(pid)
        profile["likes"] += 1
        
        await self.db.set(f"user_{user_id}", user_data)
        await self.db.set("data", data)
        await query.answer("💖 تم الإعجاب!", show_alert=True)
        
        # Send Notification (Direct Message as requested)
        if profile["user_id"] != user_id:
            try:
                username = query.from_user.username
                if username:
                    sender_id = f"@{username}" 
                else:
                    sender_id = f"{query.from_user.first_name}" # Fallback if no username
                
                msg_text = f"{sender_id}\nمعجب بك"
                
                await self.bot.send_message(
                    profile["user_id"],
                    msg_text,
                    reply_markup=Markup([
                        [Button("👀 مشاهدة ملفه", callback_data=f"view_profile:{user_id}")]
                    ])
                )
            except Exception as e:
                logger.error(f"Failed to send like notification: {e}")
        
        # Refresh
        await self.explore_profiles(_, query)

    async def handle_favorite(self, _, query: CallbackQuery) -> None:
        _, page, pid = query.data.split(":")
        user_id = query.from_user.id
        user_data = await self.db.get(f"user_{user_id}")
        
        if pid in user_data["favorites"]:
            user_data["favorites"].remove(pid)
            msg = "🗑 تم الحذف من المفضلة"
        else:
            user_data["favorites"].append(pid)
            msg = "⭐️ تم الإضافة للمفضلة"
            
        await self.db.set(f"user_{user_id}", user_data)
        await query.answer(msg, show_alert=True)

    async def view_favorites(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        user_data = await self.db.get(f"user_{user_id}")
        data = await self.db.get("data")
        
        favs = [p for p in data["profiles"] if p["id"] in user_data["favorites"]]
        if not favs: return await query.answer("📭 المفضلة فارغة", show_alert=True)
        
        text = "<b>⭐️ المفضلة:</b>\n\n"
        btns = []
        for i, p in enumerate(favs):
            verified_mark = "☑️ " if p.get('verified') else ""
            text += f"{i+1}. {verified_mark}{p['bio'][:20]}...\n"
            btns.append([
                Button(f"عرض {i+1}", callback_data=f"view_profile:{p['id']}"),
                Button(f"حذف", callback_data=f"delete_favorite:{p['id']}")
            ])
        btns.append([Button("🔙 رجوع", callback_data=f"start:{user_id}")])
        await query.message.edit_text(text, reply_markup=Markup(btns))

    async def handle_view_profile(self, _, query: CallbackQuery) -> None:
        target_identifier = query.data.split(":")[1]
        user_id = query.from_user.id
        data = await self.db.get("data")
        
        # Try to find by UUID first
        profile = next((p for p in data["profiles"] if p["id"] == target_identifier), None)
        
        # If not found, try by user_id
        if not profile:
             profile = next((p for p in data["profiles"] if str(p["user_id"]) == str(target_identifier)), None)
        
        if not profile:
            return await query.answer("❌ الملف غير موجود", show_alert=True)
            
        # Privacy Check
        age_display = profile['age'] if profile.get('show_age', True) else "🔒"
        location_display = profile['location'] if profile.get('show_location', True) else "🔒"
        verified_badge = "☑️" if profile.get('verified') else ""
        
        caption = f"""
<b>👤 الملف الشخصي {verified_badge}</b>

<b>🎂 العمر:</b> {age_display}
<b>⚧ الجنس:</b> {profile['gender']}
<b>📍 الموقع:</b> {location_display}
<b>🎨 الاهتمامات:</b> {profile['interests']}

<b>📝 نبذة:</b>
{profile['bio']}

❤️ {profile['likes']} | 👎 {profile['dislikes']}
"""
        buttons = [
            [
                Button("💖 إعجاب", callback_data=f"react:like:0:{profile['id']}"),
                Button("💌 رسالة", callback_data=f"message:{profile['user_id']}"),
                Button("⭐️ حفظ", callback_data=f"favorite:0:{profile['id']}")
            ],
            [Button("🔙 رجوع", callback_data=f"start:{user_id}")]
        ]
        
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(profile['photo_id'], caption=caption),
                reply_markup=Markup(buttons)
            )
        except:
             await query.message.delete()
             await self.bot.send_photo(query.message.chat.id, profile['photo_id'], caption=caption, reply_markup=Markup(buttons))


    def get_profile_index(self, profile, profiles):
        try: return next(i for i, p in enumerate(profiles) if p['id'] == profile['id'])
        except: return 0

    async def delete_favorite(self, _, query: CallbackQuery) -> None:
        pid = query.data.split(":")[1]
        user_id = query.from_user.id
        user_data = await self.db.get(f"user_{user_id}")
        if pid in user_data["favorites"]:
            user_data["favorites"].remove(pid)
            await self.db.set(f"user_{user_id}", user_data)
            await query.answer("تم الحذف", show_alert=True)
            await self.view_favorites(_, query)

    async def delete_profile(self, _, query: CallbackQuery) -> None:
        pid = query.data.split(":")[2]
        user_id = query.from_user.id
        data = await self.db.get("data")
        profile = next((p for p in data["profiles"] if p["id"] == pid), None)
        
        if not profile:
            return await query.answer("❌ الملف غير موجود", show_alert=True)

        if profile["user_id"] != user_id and not self.is_admin(user_id):
            return await query.answer("⛔️ غير مصرح لك بحذف هذا الملف", show_alert=True)

        idx = next((i for i, p in enumerate(data["profiles"]) if p["id"] == pid), -1)
        if idx != -1:
            data["profiles"].pop(idx)
            await self.db.set("data", data)
            await query.answer("✅ تم حذف الملف", show_alert=True)
            await self.back_to_home(_, query)

    # --- Messaging ---
    async def handle_message_click(self, _, query: CallbackQuery) -> None:
        target_id = int(query.data.split(":")[1])
        if target_id == query.from_user.id:
            return await query.answer("لا يمكنك مراسلة نفسك!", show_alert=True)
            
        chat_id = query.message.chat.id
        user_id = query.from_user.id
        
        await query.message.reply_text("<b>💌 اكتب رسالتك الآن:</b>")
        
        try:
            message = await self.bot.ask(
                chat_id=chat_id,
                filters=filters.text & filters.user(user_id)
            )
        except TimeoutError:
            return await query.message.reply_text("❌ انتهت المهلة، حاول مرة أخرى.")
            
        content = message.text
        
        # Security Check
        if not await self.security.check_message_content(content, user_id):
             return
        
        target_data = await self.db.get(f"user_{target_id}")
        if not target_data: 
            return await message.reply_text("❌ المستخدم غير موجود")
        
        msg_obj = {
            "id": str(uuid.uuid4()),
            "sender_id": user_id,
            "content": content,
            "timestamp": str(datetime.now())
        }
        
        if "messages" not in target_data: target_data["messages"] = []
        target_data["messages"].append(msg_obj)
        await self.db.set(f"user_{target_id}", target_data)
        
        await message.reply_text("✅ تم إرسال الرسالة بنجاح!")
        
        try:
            await self.bot.send_message(target_id, "💌 لديك رسالة جديدة!\nتحقق من صندوق الوارد.")
        except:
            pass

    async def view_inbox(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        user_data = await self.db.get(f"user_{user_id}")
        msgs = user_data.get("messages", [])
        
        if not msgs: return await query.answer("📭 صندوق الوارد فارغ", show_alert=True)
        
        text = "<b>💬 صندوق الوارد:</b>\n\n"
        for m in msgs[-5:]: # Show last 5
            text += f"📩 من: {m['sender_id']}\n{m['content']}\n🕒 {m['timestamp']}\n\n"
            
        await query.message.edit_text(text, reply_markup=Markup([[Button("🔙 رجوع", callback_data=f"start:{user_id}")]]))

    async def handle_matches(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        matches = await self.matching.find_matches(user_id)
        
        if not matches:
            return await query.answer("💤 لا توجد مطابقات حالياً، جرب لاحقاً!", show_alert=True)
            
        # Show best match
        match = matches[0]['profile']
        score = matches[0]['score']
        verified_badge = "☑️" if match.get('verified') else ""
        
        caption = f"""
<b>✨ أفضل مطابقة لك ({score}%) {verified_badge}:</b>

<b>👤 الاسم:</b> {match.get('name', 'مجهول')} (غير متوفر)
<b>🎂 العمر:</b> {match['age']}
<b>⚧ الجنس:</b> {match['gender']}
<b>📍 الموقع:</b> {match['location']}
<b>🎨 الاهتمامات:</b> {match['interests']}

<b>📝 نبذة:</b>
{match['bio']}
"""
        buttons = [
            [
                Button("💖 إعجاب", callback_data=f"react:like:0:{match['id']}"),
                Button("💌 رسالة", callback_data=f"message:{match['user_id']}")
            ],
            [Button("🔙 رجوع", callback_data=f"start:{user_id}")]
        ]
        
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(match['photo_id'], caption=caption),
                reply_markup=Markup(buttons)
            )
        except:
             await query.message.delete()
             await self.bot.send_photo(query.message.chat.id, match['photo_id'], caption=caption, reply_markup=Markup(buttons))

    async def handle_settings(self, _, query: CallbackQuery) -> None:
        user_id = query.from_user.id
        keyboard = await self.settings.get_settings_keyboard(user_id)
        if not keyboard:
             return await query.answer("❌ يجب عليك إنشاء ملف شخصي أولاً", show_alert=True)
             
        await query.message.edit_text("<b>⚙️ الإعدادات</b>\n\nقم بتخصيص تجربتك:", reply_markup=keyboard)

    async def handle_toggle_setting(self, _, query: CallbackQuery) -> None:
        setting = query.data.split(":")[1]
        user_id = query.from_user.id
        
        if setting == "notifications":
            user_data = await self.db.get(f"user_{user_id}")
            current = user_data.get("notifications", True)
            user_data["notifications"] = not current
            await self.db.set(f"user_{user_id}", user_data)
        elif setting in ["show_age", "show_location"]:
            profile = await self.get_user_profile(user_id)
            if profile:
                current = profile.get(setting, True)
                await self.update_profile(user_id, {setting: not current})
        
        # Refresh
        keyboard = await self.settings.get_settings_keyboard(user_id)
        await query.message.edit_reply_markup(keyboard)

    async def handle_save_settings(self, _, query: CallbackQuery) -> None:
        await query.answer("✅ تم حفظ الإعدادات", show_alert=True)
        await self.back_to_home(_, query)

    async def handle_change_target_gender(self, _, query: CallbackQuery) -> None:
        buttons = [
            [Button("رجال 👨", callback_data="set_target_gender:ذكر"), Button("نساء 👩", callback_data="set_target_gender:أنثى")],
            [Button("كلاهما 👫", callback_data="set_target_gender:كلاهما")],
            [Button("🔙 رجوع", callback_data=f"settings:{query.from_user.id}")]
        ]
        await query.message.edit_text("<b>🎯 من تبحث عنه؟</b>", reply_markup=Markup(buttons))

    async def handle_set_target_gender(self, _, query: CallbackQuery) -> None:
        target = query.data.split(":")[1]
        user_id = query.from_user.id
        
        await self.update_profile(user_id, {"target_gender": target})
        await query.answer("✅ تم حفظ التفضيلات!", show_alert=True)
        
        # Go back to settings
        await self.handle_settings(_, query)

    # --- New Features ---
    async def rate_profile(self, user_id: int, target_id: int, rating: int):
        """تقييم المستخدمين"""
        # Logic to store rating
        await self.bot.send_message(user_id, f"✅ تم تقييم المستخدم {rating}/5")

    async def start_voice_chat(self, user_id: int, target_id: int):
        """بدء محادثة صوتية"""
        # In Telegram, we can't force a voice chat easily between two users via bot, 
        # but we can generate a link or suggest a call.
        await self.bot.send_message(user_id, "📞 هذه الميزة قيد التطوير.")

    async def create_event(self, user_id: int, event_data: dict):
        """إنشاء حدث تعارف"""
        # Logic to create event
        pass

    async def report_user(self, reporter_id: int, reported_id: int, reason: str):
        """الابلاغ عن مستخدم"""
        for admin in self.admin_ids:
             await self.bot.send_message(admin, f"🚨 <b>بلاغ جديد!</b>\n\nالمُبَلِّغ: {reporter_id}\nالمُبَلَّغ عنه: {reported_id}\nالسبب: {reason}")
        await self.bot.send_message(reporter_id, "✅ تم استلام بلاغك.")

    async def send_error_message(self, chat_id: int) -> None:
        try:
            await self.bot.send_message(chat_id, "⚠️ عذراً، حدث خطأ ما.")
        except: pass

    def run(self):
        logger.info("Starting Dating Bot...")
        self.bot.run()

if __name__ == "__main__":
    BOT_TOKEN = "8218858347:AAHhUsdyW_055YCNF_FNIiwn4q4OvHhSNrk"
    ADMIN_IDS = [6224395577]
    dating_bot = DatingBot(BOT_TOKEN, ADMIN_IDS)
    dating_bot.run()
