EN = {
    # Onboarding
    "welcome":          "👋 Welcome to *Vault Bot*!\n\nAn encrypted vault for passwords, seed phrases and personal data.\n\nChoose your language:",
    "choose_lang":      "🌐 Choose language / Выбери язык:",
    "lang_set":         "✅ Language set: English",
    "set_master":       "🔑 Create a *master password*.\n\nIt encrypts all your data. We don't store it — only a hash for verification.\n\n⚠️ If you forget it — data cannot be recovered.\n\nEnter master password (minimum 8 characters):",
    "master_too_short": "❌ Password too short. Minimum 8 characters.",
    "confirm_master":   "🔁 Repeat master password:",
    "master_mismatch":  "❌ Passwords don't match. Try again.",
    "master_set":       "✅ Master password set!\n\n",
    "enter_master":     "🔐 Enter master password to unlock:",
    "wrong_master":     "❌ Wrong master password.",
    "enter_pin":        "🔢 Enter PIN code (4 digits):",
    "wrong_pin":        "❌ Wrong PIN. Try again.",
    "locked":           "🔒 Vault is locked. Enter PIN or master password.",
    "unlocked":         "🔓 Vault unlocked.",

    # Main menu
    "menu":             "🔐 *Vault Bot* — main menu\n\nPlan: {plan} | Entries: {count}",
    "btn_add":          "➕ Add",
    "btn_list":         "📋 List",
    "btn_search":       "🔍 Search",
    "btn_favorites":    "⭐ Favorites",
    "btn_generate":     "⚙️ Generator",
    "btn_backup":       "💾 Backup",
    "btn_subscribe":    "💎 Subscribe",
    "btn_settings":     "⚙️ Settings",

    # Tutorial
    "tutorial": (
        "📖 *Quick Tutorial:*\n\n"
        "➕ /add — add an entry\n"
        "📋 /list — browse by category\n"
        "🔍 /search — search all data\n"
        "⭐ /favorites — starred entries\n"
        "⚙️ /generate — passwords & seed phrases\n"
        "💾 /backup — encrypted backup\n"
        "🔢 /setpin — set PIN code\n"
        "💎 /subscribe — plans & payment\n"
        "👥 /refer — referral link\n\n"
        "🆓 Free: 10 entries, Passwords & Notes only\n"
        "💎 Lifetime for 1450⭐: everything unlimited forever\n"
        "🚀 Premium for 450⭐/mo: all features + weekly auto-backup"
    ),

    # Add entry
    "add_choose_cat":   "📂 Choose a category:",
    "add_name":         "✏️ Enter entry name:",
    "add_content":      "📝 Enter content (password, seed, text...):",
    "add_tags":         "🏷️ Add tags separated by commas (or /skip):",
    "add_done":         "✅ Entry *{name}* saved in {cat}.",
    "add_cancelled":    "❌ Adding cancelled.",

    # List
    "list_choose_cat":  "📂 Choose a category to view:",
    "list_empty":       "📭 Category *{cat}* is empty.",
    "list_header":      "📋 *{cat}* — {count} entries:",
    "entry_line":       "{fav}*{name}*{tags}\n   └ /get_{id}  /del_{id}  /fav_{id}",

    # View entry
    "entry_view":       "🔓 *{name}*\n📂 {cat}\n🏷️ {tags}\n\n`{content}`\n\n_(deletes in 10 sec)_",
    "entry_not_found":  "❌ Entry not found.",

    # Search
    "search_prompt":    "🔍 Enter search query (name or tag):",
    "search_empty":     "🔍 Nothing found for *{query}*.",
    "search_results":   "🔍 Results for *{query}* ({count}):",

    # Favorites
    "fav_empty":        "⭐ No favorite entries.",
    "fav_header":       "⭐ Favorites — {count} entries:",
    "fav_toggled":      "⭐ Favorite status updated.",

    # Generator
    "gen_menu":         "⚙️ *Generator*\n\nChoose what to generate:",
    "gen_password":     "🔑 Generating password...",
    "gen_seed12":       "🌱 Generating 12-word seed phrase...",
    "gen_seed24":       "🌱 Generating 24-word seed phrase...",
    "gen_result_pass":  "🔑 *Password* (16 chars):\n\n`{value}`\n\n_(deletes in 10 sec)_",
    "gen_result_seed":  "🌱 *Seed phrase* ({words} words):\n\n`{value}`\n\n⚠️ Save immediately!\n_(deletes in 10 sec)_",
    "btn_gen_pass":     "🔑 Password 16 chars",
    "btn_gen_seed12":   "🌱 Seed 12 words",
    "btn_gen_seed24":   "🌱 Seed 24 words",

    # PIN
    "pin_prompt":       "🔢 Enter new PIN code (4 digits):",
    "pin_confirm":      "🔁 Repeat PIN code:",
    "pin_mismatch":     "❌ PIN codes don't match. Try again.",
    "pin_set":          "✅ PIN code set.",
    "pin_invalid":      "❌ PIN must be 4 digits.",

    # Backup
    "backup_start":     "💾 Creating encrypted backup...",
    "backup_done":      "✅ Backup created. File is encrypted with your master password.\n\n🔒 To restore use /restore",
    "backup_premium":   "💎 Auto-backup is available on Premium plan only.\n\nGet a subscription: /subscribe",
    "restore_prompt":   "📂 Send backup file (.json):",
    "restore_done":     "✅ Restored {count} entries.",
    "restore_error":    "❌ Restore error. Check the file and master password.",

    # Subscribe / paywall
    "plan_free":        "🆓 Free",
    "plan_onetime":     "💎 Lifetime",
    "plan_premium":     "🚀 Premium",
    "subscribe_menu": (
        "💎 *Vault Bot Plans*\n\n"
        "🆓 *Free* — free\n"
        "• 10 entries max\n"
        "• Passwords & Notes only\n\n"
        "💎 *Lifetime* — 1450⭐ (~$29) one-time\n"
        "• All 8 categories\n"
        "• Unlimited entries\n"
        "• Forever\n\n"
        "🚀 *Premium* — 450⭐/mo (~$9)\n"
        "• All Lifetime features\n"
        "• Password & seed phrase generators\n"
        "• Auto-backup every Sunday\n"
        "• Priority support\n\n"
        "Your plan: *{plan}*"
    ),
    "btn_buy_onetime":  "💎 Buy Lifetime — 1450⭐",
    "btn_buy_premium":  "🚀 Premium — 450⭐/mo",
    "already_premium":  "✅ You already have an active Premium plan.",
    "already_onetime":  "✅ You already have Lifetime access.",
    "payment_success_onetime": "🎉 *Lifetime access activated!*\n\nUnlimited vault and all categories are yours.",
    "payment_success_premium": "🚀 *Premium activated!*\n\nAuto-backup, generators and everything else — enjoy!",

    # Paywall
    "paywall": (
        "⚠️ *Free plan limit reached*\n\n"
        "Free plan allows maximum 10 entries.\n\n"
        "💎 *Lifetime for 1450⭐* — unlimited forever\n"
        "🚀 *Premium for 450⭐/mo* — + auto-backup\n\n"
        "Choose a plan:"
    ),
    "paywall_cat": (
        "⚠️ *Category unavailable on Free plan*\n\n"
        "Category {cat} is available in paid plans.\n\n"
        "💎 *Lifetime for 1450⭐* — all categories forever\n\n"
        "Get it: /subscribe"
    ),

    # Referral
    "refer_text": (
        "👥 *Referral Program*\n\n"
        "Your link:\n`{link}`\n\n"
        "For each invited friend:\n"
        "• +30 days Premium\n"
        "• If friend buys Lifetime → you get +145⭐ (10%)\n\n"
        "Invited so far: {count} people"
    ),

    # Language
    "lang_menu":        "🌐 Choose language:",
    "btn_ru":           "🇷🇺 Русский",
    "btn_en":           "🇬🇧 English",

    # Delete
    "delete_confirm":   "🗑️ Delete entry *{name}*?",
    "btn_yes_delete":   "✅ Yes, delete",
    "btn_cancel":       "❌ Cancel",
    "deleted":          "✅ Entry deleted.",

    # Errors
    "error":            "❌ Something went wrong. Please try again.",
    "cancelled":        "❌ Cancelled.",
    "rate_limit":       "⏳ Too many requests. Please wait a minute.",

    # Admin
    "admin_stats": (
        "📊 *Bot Statistics*\n\n"
        "👤 Total users: {total_users}\n"
        "🆓 Free: {free_users}\n"
        "💎 Paid: {paid_users}\n"
        "📝 Entries: {total_entries}\n"
        "⭐ Revenue: {total_revenue_stars} Stars\n"
        "🆕 New today: {new_today}"
    ),
    "not_admin":        "🚫 Admin only.",
}
