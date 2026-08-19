# translations.py

LANGUAGES = {
    "ar": {
        # صفحة السيرفرات (guilds.html)
        "select_server_title": "اختر السيرفر | لوحة التحكم",
        "verified_badge": "البوت موثق على الديسكورد",
        "your_servers": "سيرفراتك المتاحة",
        "server_settings": "إعدادات السيرفر",
        
        # لوحة التحكم الرئيسية (index.html)
        "dashboard_title": "لوحة تحكم السيرفر",
        "back_to_servers": "قائمة السيرفرات",
        
        # القوائم الجانبية
        "tab_media": "قنوات الميديا",
        "tab_banned": "الكلمات المحظورة",
        "tab_responses": "الردود التلقائية",
        "tab_roles": "الرول واللقب",
        "tab_farewell": "إعدادات الوداع",
        "tab_tickets": "نظام التذاكر",
        "tab_xp": "نظام المستويات",
        
        # محتوى الأقسام (قنوات الميديا)
        "media_header": "إعدادات قنوات الميديا",
        "media_select_label": "اختر قنوات الميديا (اضغط Ctrl لمضاعفة الاختيار):",
        "media_warning_label": "رسالة التحذير المخصصة للميديا:",
        "media_warning_note": "ملاحظة: يمكنك استخدام التاج {user} للإشارة للعضو.",
        
        # الكلمات المحظورة
        "banned_header": "نظام حظر الكلمات والعقوبات",
        "banned_words_label": "الكلمات المحظورة (افصل بينها بفصلة ,):",
        "warning_title_label": "عنوان رسالة التحذير:",
        "max_violations_label": "الحد الأقصى للمخالفات قبل العقوبة:",
        "warn_msg_1_label": "رسالة التحذير الأول:",
        "warn_msg_2_label": "رسالة التحذير الثاني:",
        "punishment_type_label": "نوع العقوبة:",
        "timeout_duration_label": "مدة التايم أوت (بالدقائق):",
        
        # خيارات العقوبات
        "opt_timeout": "تايم أوت (Timeout)",
        "opt_mute": "كتم كامل (Mute)",
        "opt_kick": "طرد (Kick)",
        
        # الردود التلقائية
        "responses_header": "الردود التلقائية",
        
        # الرول واللقب
        "roles_header": "الرول واللقب التلقائي",
        "auto_role_label": "الرول التلقائي للأعضاء الجدد:",
        "no_role": "-- بدون رول --",
        "auto_nickname_label": "اللقب التلقائي (Auto-Nickname):",
        "auto_nickname_note": "استخدم {user} لاسم العضو أو اكتب كلمة لتكون بادئة.",
        
        # الوداع
        "farewell_header": "إعدادات رسالة الوداع",
        "farewell_channel_label": "قناة الوداع:",
        "stop_farewell": "-- إيقاف رسائل الوداع --",
        "farewell_title_label": "عنوان إمبد الوداع:",
        "farewell_desc_label": "وصف رسالة الوداع:",
        "farewell_desc_note": "يمكنك استخدام {user} للإشارة لمن غادر.",
        "farewell_img_label": "رابط صورة الوداع (URL):",
        "farewell_action_label": "إجراء الزر التفاعلي مع المغادرة:",
        "farewell_action_none": "بدون إجراء (زر عادي)",
        "farewell_action_ban": "زر الحظر (Ban)",
        "farewell_action_timeout": "زر التايم أوت (Timeout)",
        
        # التذاكر
        "tickets_header": "إعدادات نظام التذاكر",
        "ticket_category_label": "قسم التذاكر (Category):",
        "select_category": "-- اختر القسم --",
        "ticket_support_role_label": "رول الدعم الفني:",
        "select_role": "-- اختر الرول --",
        
        # المستويات
        "xp_header": "نظام المستويات (XP)",
        "xp_status_label": "حالة نظام المستويات:",
        "xp_enabled": "مفعل",
        "xp_disabled": "معطل",
        "xp_amount_label": "كمية XP لكل رسالة:",
        "xp_role_5": "رول المستوى 5:",
        "xp_role_10": "رول المستوى 10:",
        "xp_role_20": "رول المستوى 20:",
        "select_xp_role": "-- اختر رول --",
        
        # الزر والحفظ
        "save_settings": "حفظ الإعدادات",
        "save_success": "تم حفظ التعديلات بنجاح ✨",
    },
    "en": {
        # صفحة السيرفرات (guilds.html)
        "select_server_title": "Select Server | Dashboard",
        "verified_badge": "Bot is Verified on Discord",
        "your_servers": "Your Available Servers",
        "server_settings": "Server Settings",
        
        # لوحة التحكم الرئيسية (index.html)
        "dashboard_title": "Server Dashboard",
        "back_to_servers": "Servers List",
        
        # القوائم الجانبية
        "tab_media": "Media Channels",
        "tab_banned": "Banned Words",
        "tab_responses": "Auto Responses",
        "tab_roles": "Roles & Nickname",
        "tab_farewell": "Farewell Settings",
        "tab_tickets": "Ticket System",
        "tab_xp": "XP System",
        
        # محتوى الأقسام (قنوات الميديا)
        "media_header": "Media Channels Settings",
        "media_select_label": "Select Media Channels (Hold Ctrl for multiple):",
        "media_warning_label": "Custom Media Warning Message:",
        "media_warning_note": "Note: You can use the {user} tag to mention the member.",
        
        # الكلمات المحظورة
        "banned_header": "Banned Words & Punishments System",
        "banned_words_label": "Banned Words (separate with comma ,):",
        "warning_title_label": "Warning Message Title:",
        "max_violations_label": "Max Violations Before Punishment:",
        "warn_msg_1_label": "First Warning Message:",
        "warn_msg_2_label": "Second Warning Message:",
        "punishment_type_label": "Punishment Type:",
        "timeout_duration_label": "Timeout Duration (Minutes):",
        
        # خيارات العقوبات
        "opt_timeout": "Timeout",
        "opt_mute": "Mute",
        "opt_kick": "Kick",
        
        # الردود التلقائية
        "responses_header": "Auto Responses",
        
        # الرول واللقب
        "roles_header": "Auto Role & Nickname",
        "auto_role_label": "Auto Role for New Members:",
        "no_role": "-- No Role --",
        "auto_nickname_label": "Auto-Nickname:",
        "auto_nickname_note": "Use {user} for member's name or add a prefix word.",
        
        # الوداع
        "farewell_header": "Farewell Message Settings",
        "farewell_channel_label": "Farewell Channel:",
        "stop_farewell": "-- Disable Farewell Messages --",
        "farewell_title_label": "Farewell Embed Title:",
        "farewell_desc_label": "Farewell Description:",
        "farewell_desc_note": "You can use {user} to mention the person who left.",
        "farewell_img_label": "Farewell Image URL:",
        "farewell_action_label": "Farewell Interactive Button Action:",
        "farewell_action_none": "No Action (Normal Button)",
        "farewell_action_ban": "Ban Button",
        "farewell_action_timeout": "Timeout Button",
        
        # التذاكر
        "tickets_header": "Ticket System Settings",
        "ticket_category_label": "Ticket Category:",
        "select_category": "-- Select Category --",
        "ticket_support_role_label": "Support Role:",
        "select_role": "-- Select Role --",
        
        # المستويات
        "xp_header": "XP System (Levels)",
        "xp_status_label": "XP System Status:",
        "xp_enabled": "Enabled",
        "xp_disabled": "Disabled",
        "xp_amount_label": "XP per message:",
        "xp_role_5": "Level 5 Role:",
        "xp_role_10": "Level 10 Role:",
        "xp_role_20": "Level 20 Role:",
        "select_xp_role": "-- Select Role --",
        
        # الزر والحفظ
        "save_settings": "Save Settings",
        "save_success": "Changes saved successfully ✨",
    }
}

def _(lang, key):
    return LANGUAGES.get(lang, LANGUAGES["ar"]).get(key, LANGUAGES["ar"].get(key, key))
