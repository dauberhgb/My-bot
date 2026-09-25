import os
from openai import OpenAI

def scan_codebase():
    # 1. الاتصال بـ OmniRoute باستخدام متغيرات البيئة
    client = OpenAI(
        base_url=os.getenv("OMNIROUTE_BASE_URL"),
        api_key=os.getenv("OMNIROUTE_API_KEY")
    )

    # 2. قراءة ملف main.py (أو أي ملف آخر تريد فحصه)
    try:
        with open("main.py", "r", encoding="utf-8") as f:
            code_content = f.read()
    except FileNotFoundError:
        print("❌ الملف غير موجود.")
        return

    print("🔍 جاري إرسال الكود إلى OmniRoute للفحص الأمني وتصحيح الأخطاء...")

    # 3. إرسال الكود للذكاء الاصطناعي للمراجعة والتدقيق
    response = client.chat.completions.create(
        model="gemini-1.5-pro",
        messages=[
            {
                "role": "system",
                "content": "أنت نظام ذكاء اصطناعي فاحص للأكواد البرمجية ومطور أمن سيبراني متخصص في بايثون وديسكورد."
            },
            {
                "role": "user",
                "content": f"قم بفحص هذا الكود بحثاً عن الثغرات الأمنية، أخطاء الأداء، أو مشاكل الاتصال بقاعدة البيانات، واعطني التقرير والكود المحسّن:\n\n{code_content}"
            }
        ]
    )

    # 4. طباعة التقرير والإصلاحات المقترحة
    print("\n--- 🛡️ تقرير الفحص الأمني من OmniRoute ---")
    print(response.choices[0].message.content)

if __name__ == "__main__":
    scan_codebase()
