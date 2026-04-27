from typing import Any, Callable

LEXICON_COMMANDS_RU: dict[str, str] = {
    "/start_description": "Запуск бота",
    "/help_description": "Справка по работе бота",
    "/subscription_description": "Проверить подписки",
    "/chat_description": "Чат с AI-менеджером",
    "/statistics_description": "Статистика",
    "/admin_description": "Панель администратора",
    "/ban_description": "Забанить пользователя (требует user_id или username)",
    "/unban_description": "Разбанить пользователя (требует user_id или username)",
}

LEXICON_ADMIN_BUTTONS_RU: dict[str, str] = {
    "statistics_button": "Статистика",
    "newsletter_button": "Создать рассылку",
    "ban_user_button": "Забанить",
    "unban_user_button": "Разбанить",
    "exit_button": "Выйти",
    "add_button": "Да",
    "no_button": "Нет",
    "confirm_sender": "Подтвердить",
    "cancel_sender": "Отменить",
}

LEXICON_ADMIN_RU: dict[str, str] = {
    "admin_panel_enter_ban": "Введите <b>user_id</b> (число) или <b>@username</b> пользователя, которого нужно забанить.",
    "admin_panel_enter_unban": "Введите <b>user_id</b> (число) или <b>@username</b> пользователя, которого нужно разбанить.",
    "admin_mailing_in_progress": "Сначала завершите или отмените создание рассылки: нажмите «Выйти» в панели и при необходимости начните снова.",
    "empty_ban_answer": "Вы не ввели аргумент для бана",
    "empty_unban_answer": "Вы не ввели аргумент для разбана",
    "incorrect_unban_arg": "Некорректный аргумент для разбана",
    "incorrect_ban_arg": "Некорректный аргумент для бана",
    "no_user": "Пользователь не найден",
    "already_banned": "Пользователь уже забанен",
    "successfully_banned": "Пользователь успешно забанен",
    "successfully_unbanned": "Пользователь успешно разбанен",
    "not_banned": "Пользователь не забанен",
}

LEXICON_RU: dict[str, Callable[[Any], str] | str] = {
    "/start_text": lambda x: (
        f"Здравствуйте, <b>{x}</b>! Компания AmericaTrade рада приветствовать Вас!\r\n\n"
        "Если Вы планируете приобрести автомобиль из США, Вы обратились по адресу!\r\n\n"
        "Здесь Вы можете:\r\n\n"
        "- Узнать все об американских автомобилях.\r\n"
        "- Воспользоваться бесплатной консультацией от нашего эксперта.\r\n"
        "- Получать реальные варианты с аукционов прямо здесь, в Telegram!\r\n"
        "- Подписаться на обновления по интересующим Вас маркам и моделям авто.\r\n"
        "- Первыми видеть самые 'ГОРЯЧИЕ' лоты на аукционах.\r\n\n"
        "Пора воплотить мечту об американском авто в реальность! Готовы начать?"
    ),
    "/help_text": "Я ваш личный помощник по подбору авто из США.\r\n"
    "Хотите выгодно купить авто из США? Я помогу!\r\n"
    "Получите доступ к лучшим предложениям американских аукционов прямо здесь.\r\n"
    "Подпишитесь на интересующие вас модели и будьте в курсе самых свежих обновлений!\r\n\n"
    "➡ Комманда /start - запуск бота.\r\n"
    "➡ Комманда /help - помощь по работе с ботом.\r\n"
    "➡ Комманда /subscription - редактирование ваших подписок.\r\n"
    "➡ Комманда /chat - чат с AI-менеджером.\r\n",
    "contacts_text": "<b>Наши контакты:</b>\r\n\n"
    "📞 <b>+375 44 723-24-25</b>\r\n"
    "<a href='https://www.instagram.com/americatrade.by'>📱 Instagram</a>\r\n"
    "<a href='https://t.me/americatradeby'>📱 Telegram</a>\r\n\n"
    "🗺️ <b>г.Минск, ул.Либаво-Роменская, 23, офис 816</b>\r\n"
    "Email: info@americatrade.by",
    "more_information_text": "<b>Авто из США 🇺🇸 </b>\r\n\n"
    "AmericaTrade – один из лидеров в вопросах подбора автомобилей из Америки.\r\n"
    "Работаем прозрачно, поэтому можем предложить очень низкие цены на авто.\r\n"
    "Мы ценим своих клиентов и сопровождаем их на всех этапах сотрудничества.\r\n"
    "Благодаря этому наши клиенты получают проверенный автомобиль без переплат и сюрпризов.\r\n\n"
    "Компания AmericaTreade предоставляет полный комплекс услуг по подбору авто из США с реальной денежной выгодой до 40% от автопарка РБ.\r\n"
    "- Без первого взноса. Начинаем подбор авто сразу после заключения договора.\r\n"
    "- Полное сопровождение. Менеджер будет с Вами на связи вплоть до постановки авто на учет.\r\n"
    "- Оплата через банк. Все платежи осуществляются исключительно через банк, никаких наличных и подозрительных переводов.",
    "advantages_text": "Почему нас выбирают?\r\n\n"
    "Главное преимущество — это экономия.\r\n"
    "Автомобили из США приезжают с выгодой до 40% от авторынка РБ.\r\n"
    "- Опыт. Компания существует на рынке более 15 лет. Мы знаем все тонкости таможенного законодательства РБ и можем подобрать для вас оптимальный вариант авто.\r\n"
    "- Цены. Мы предлагаем доступные цены на наши услуги. Также всегда готовы обсудить условия сотрудничества и предложить вам наиболее выгодный вариант.\r\n"
    "- Репутация. За все время мы получили огромное количество положительных отзывов. Всегда оперативно и с максимальным профессионализмом находим подход к каждому клиенту.\r\n"
    "- Надёжность. Работаем только по договору. Все оплаты производятся исключительно через банк (без скрытых платежей и комиссий).\r\n"
    "- Лицензированный дилер. Наш брокер имеет все необходимые лицензии для покупки авто и официально зарегистрированное юр. лицо на территории США.",
    "purchasing_process_text": "Как происходи процесс покупки?\r\n\n"
    "Американский рынок техники поражает своим масштабом и разнообразием. Здесь можно найти практически любое транспортное средство\r\n"
    "для самых разных целей: от автомобилей и мотоциклов до специализированных машин.\r\n\n"
    "1. Подбор вариантов\r\n"
    "Подбираем варианты авто согласно Вашим предпочтениям, делаем детальный расчет конечной стоимости. Присылаем Вам варианты в любой удобный для вас мессенджер, либо вместе рассматриваем у нас в офисе.\r\n\n"
    "2. Заключение договора\r\n"
    "Заключаем договор на оказание услуг (в офисе либо удаленно). Оплата производится официально через банк либо ЕРИП / Интернет-банкинг.\r\n\n"
    "3. Участие в аукционе\r\n"
    "Участвуем в аукционе, предварительно согласовав с Вами максимальную ставку и рассчитав итоговую стоимость на выбранный автомобиль. Неограниченное участие в аукционах!\r\n\n"
    "4. Покупка и оплата\r\n"
    "После выигрыша на аукционе подготавливаются все необходимые документы. Затем выставляем официальный счет (инвойс), по которому Вы производите оплату за авто и доставку в банке.\r\n\n"
    "5. Доставка\r\n"
    "После оплаты автомобиль доставляется в порт, подготавливается вся документация. Далее происходит погрузка на корабль.\r\n\n"
    "6. Таможенное оформление\r\n"
    "Мы заранее сообщаем Вам о времени прибытия авто на таможню, помогаем с документами. Вы оплачиваете таможенную пошлину, после чего забираете приобретенный автомобиль.",
    "car_delivery_text": "Как осуществляется доставка в РБ?\r\n\n"
    "Обращаем Ваше внимание, что несмотря на значительное санкционное давление, экспорт авто из США доступен и осуществляется в обычном режиме — логистика налажена.\r\n"
    "Маршрут стандартный: США → Порт Клайпеда (Литва) / Поти (Грузия) → Минск.\r\n\n"
    "Транспортировка по США ~ 2-5 дней\r\n"
    "После выигрыша авто на аукционе и получения документов автомобиль доставляется в ближайший порт.\r\n\n"
    "Консолидация в порту ~ 3-10 дней\r\n"
    "В порту автомобиль загружается в контейнер и ожидает погрузки на корабль.\r\n\n"
    "Доставка из США в Беларусь ~ 20-25 дней\r\n"
    "Подготовка документов для отправки авто из США. Погрузка контейнера на корабль и отправка в РБ.\r\n\n"
    "Получение в пункте назначения ~ 1-2 дня\r\n"
    "Контейнер с автомобилем прибывает на склад временного хранения для дальнейшей таможенной очистки.",
    "choose_a_car_text": "Уже определились какой автомобиль хотите?",
    "nothing_found_text": "УПС...\r\n"
    "К сожалению на данный момент на аукционе нет вариантов под Ваши критерии.",
    "no_more_cars_text": "Больше вариантов не найдено.",
    "cars_describe_text": "Актуальные варианты на аукционе под Ваши критерии:",
    "top_cars_text": "ТОП 3 Авто по Вашим параметрам:",
    "assisted_gallery_result_text": "Пример из подборки по вашим критериям — такой класс авто мы можем искать на аукционе:",
    "assisted_gallery_empty_text": "Пока нет примеров для этой комбинации кузова и бюджета. Попробуйте другой бюджет или оставьте заявку — подберём вручную.",
    "popular_models_text": "Ниже представлены самые популярные модели по Вашим критериям:",
    "application_for_selection_text": "Укажите Ваше имя",
    "choose_phone_request_text": "Нажмите кнопку <b>Отправить номер телефона</b>, ",
    "phone_request_answer_text": "Отлично. Наш менеджер свяжется с Вами в ближайшее время.",
    "phone_request_answer_text_v2": "Ваша заявка принята. Наш менеджер свяжется с Вами в ближайшее время.",
    "yes_subscription_text": lambda count: (
        f"Вы успешно подписались на обновления по выбранному авто.\r\n\nОсталось подписок: {count}"
    ),
    "no_subscription_text": lambda count: (
        f"Ваш лимит достигнут.\r\n\nОсталось подписок: {count}"
    ),
    "subscriptions_text": "Ваши подписки:",
    "no_subscriptions_text": "У Вас нет актуальных подписок",
    "subscriptions_list_text": "Вы подписаны на следующие автомобили👇:",
    "subscription_deleted_text": "Подписка успешно удалена",
    "subscription_not_found_text": "Подписка не найдена",
    "call_request_answer_text": "Спасибо! Ниже ссылки на сайт и отзывы — также можете написать нам в мессенджерах.",
    "unknown_message_hint_text": "Используйте меню или Чат с AI-менеджером.",
}

LEXICON_BUTTONS_RU: dict[str, str] = {
    "choose_a_car_button": "Подобрать авто",
    "more_information_button": "Все об авто из США",
    "contact_button": "Контакты",
    "url_site_button": "Наш сайт",
    "reviews_yandex_button": "Отзывы Яндекс",
    "reviews_google_button": "Отзывы Google",
    "back_to:main_menu": "🔙 Вернуться в начало",
    "back_to:more_info": "🔙 Назад",
    "advantages_button": "Преимущества работы с нами",
    "purchasing_process_button": "Процесс покупки авто из США",
    "car_delivery_button": "Доставка авто из США",
    "knowing_button": "Выбрать марку и модель",
    "advice_button": "Нужна помощь в выборе",
    "new_search_button": "Новый поиск",
    "new_search_button_assisted": "Новый поиск",
    "new_search_button_self": "Новый поиск",
    "subscription_button": "Подписаться",
    "else_car_button": "Подобрать еще",
    "application_for_selection_button": "Оставить заявку на бесплатный подбор",
    "delete_subscription_button": "❌ Удалить",
    "phone_number_button": "Отправить номер телефона",
}


LEXICON_FORM_BUTTONS_RU: dict[str, Callable[[Any], str]] = {
    "brand_buttons": [
        "ACURA",
        "ALFA ROMEO",
        "AUDI",
        "BMW",
        "BUICK",
        "CADILLAC",
        "CHEVROLET",
        "CHRYSLER",
        "DODGE",
        "FIAT",
        "FORD",
        "GMC",
        "HONDA",
        "HYUNDAI",
        "INFINITI",
        "JAGUAR",
        "JEEP",
        "KIA",
        "LAND ROVER",
        "LEXUS",
        "LINCOLN",
        "MAZDA",
        "MERCEDES-BENZ",
        "MINI",
        "MITSUBISHI",
        "NISSAN",
        "PORSCHE",
        "SUBARU",
        "TESLA",
        "TOYOTA",
        "VOLKSWAGEN",
        "VOLVO",
    ],
    "model_buttons": {
        "ACURA": ["ALL MODELS", "ILX", "MDX", "RDX", "TL", "TLX", "TSX"],
        "ALFA ROMEO": ["GIULIA", "STELVIO"],
        "AUDI": [
            "ALL MODELS",
            "A3",
            "A4",
            "A5",
            "A6",
            "A7",
            "A8",
            "E-TRON",
            "Q3",
            "Q5",
            "Q7",
            "Q8",
            "S3",
            "S4/RS4",
            "S5/RS5",
            "S6/RS6",
            "SQ5",
            "TT",
        ],
        "BMW": [
            "ALL MODELS",
            "1 SERIES",
            "2 SERIES",
            "3 SERIES",
            "4 SERIES",
            "5 SERIES",
            "6 SERIES",
            "7 SERIES",
            "M2",
            "M3",
            "M4",
            "M5",
            "X1",
            "X2",
            "X3",
            "X4",
            "X5",
            "X6",
            "X7",
            "Z4",
        ],
        "BUICK": ["ALL MODELS", "ENCLAVE", "ENCORE", "ENVISION", "LACROSSE", "REGAL"],
        "CADILLAC": [
            "ALL MODELS",
            "ATS",
            "CT4",
            "CT5",
            "CT6",
            "CTS",
            "ESCALADE",
            "XT4",
            "XT5",
            "XT6",
            "XTS",
        ],
        "CHEVROLET": [
            "ALL MODELS",
            "BLAZER",
            "CAMARO",
            "COBALT",
            "COLORADO",
            "CRUZE",
            "EQUINOX",
            "MALIBU",
            "SILVERADO",
            "SONIC",
            "SPARK",
            "SUBURBAN",
            "TAHOE",
            "TRAILBLZR",
            "TRAVERSE",
            "TRAX",
        ],
        "CHRYSLER": ["ALL MODELS", "MINIVAN", "PACIFICA"],
        "DODGE": [
            "ALL MODELS",
            "CARAVAN",
            "CHALLENGER",
            "CHARGER",
            "DURANGO",
            "JOURNEY",
            "RAM 1500",
            "RAM 2500",
            "RAM 3500",
        ],
        "FIAT": ["ALL MODELS", "500"],
        "FORD": [
            "ALL MODELS",
            "BRONCO",
            "CMAX",
            "ECONOLINE",
            "ECOSPORT",
            "EDGE",
            "ESCAPE",
            "EXPEDITION",
            "EXPLORER",
            "F-150",
            "F250",
            "F350",
            "FIESTA",
            "FLEX",
            "FOCUS",
            "FUSION",
            "MUSTANG",
            "RANGER",
            "TAURUS",
        ],
        "GMC": ["ALL MODELS", "ACADIA", "SIERRA", "TERRAIN", "YUKON"],
        "HONDA": [
            "ALL MODELS",
            "ACCORD",
            "CIVIC",
            "CLARITY",
            "CRV",
            "FIT",
            "HR-V",
            "INSIGHT",
            "ODYSSEY",
            "PILOT",
            "RIDGELINE",
        ],
        "HYUNDAI": [
            "ALL MODELS",
            "ELANTRA",
            "GENESIS",
            "IONIQ",
            "KONA",
            "PALISADE",
            "SANTA FE",
            "SONATA",
            "TUCSON",
            "VELOSTER",
            "VENUE",
        ],
        "INFINITI": [
            "ALL MODELS",
            "Q50",
            "Q60",
            "QX30",
            "QX50",
            "QX56",
            "QX60",
            "QX80",
        ],
        "JAGUAR": ["ALL MODELS", "F-PACE", "F-TYPE", "I-PACE", "XE", "XF", "XJ"],
        "JEEP": [
            "ALL MODELS",
            "CHEROKEE",
            "COMPASS",
            "GRAND CHER",
            "PATRIOT",
            "RENEGADE",
            "WRANGLER",
        ],
        "KIA": [
            "ALL MODELS",
            "FORTE",
            "K5",
            "NIRO",
            "OPTIMA",
            "SORENTO",
            "SOUL",
            "SPORTAGE",
            "STINGER",
        ],
        "LAND ROVER": ["ALL MODELS", "DEFENDER", "DISCOVERY", "RANGEROVER"],
        "LEXUS": ["ALL MODELS", "ES350", "GX", "IS", "LX470", "NX", "RX350"],
        "LINCOLN": [
            "ALL MODELS",
            "AVIATOR",
            "CONTINENTL",
            "CORSAIR",
            "MKC",
            "MKX",
            "MKZ",
            "NAUTILUS",
            "NAVIGATOR",
        ],
        "MAZDA": [
            "ALL MODELS",
            "3",
            "6",
            "CX-3",
            "CX-5",
            "CX-7",
            "CX-9",
            "CX30",
            "MX5",
        ],
        "MERCEDES-BENZ": [
            "ALL MODELS",
            "A-CLASS",
            "C-CLASS",
            "CLA-CLASS",
            "CLS-CLASS",
            "E-CLASS",
            "GL-CLASS",
            "GLA-CLASS",
            "GLB-CLASS",
            "GLC-CLASS",
            "GLE-CLASS",
            "GLS-CLASS",
            "S-CLASS",
        ],
        "MINI": ["ALL MODELS", "COOPER"],
        "MITSUBISHI": ["ALL MODELS", "ECLIPSE", "MIRAGE", "OUTLANDER"],
        "NISSAN": [
            "ALL MODELS",
            "ALTIMA",
            "KICKS",
            "LEAF",
            "MAXIMA",
            "MURANO",
            "PATHFINDER",
            "ROGUE",
            "SENTRA",
            "VERSA",
        ],
        "PORSCHE": [
            "ALL MODELS",
            "911",
            "BOXSTER",
            "CAYENNE",
            "CAYMAN",
            "MACAN",
            "PANAMERA",
            "TAYCAN",
        ],
        "SUBARU": [
            "ALL MODELS",
            "ASCENT",
            "BRZ",
            "CROSSTREK",
            "FORESTER",
            "IMPREZA",
            "LEGACY",
            "OUTBACK",
        ],
        "TESLA": ["ALL MODELS", "MODEL 3", "MODEL S", "MODEL X", "MODEL Y"],
        "TOYOTA": [
            "ALL MODELS",
            "4RUNNER",
            "CAMRY",
            "COROLLA",
            "HIGHLANDER",
            "PRIUS",
            "RAV4",
            "SEQUOIA",
            "SIENNA",
            "TACOMA",
            "TUNDRA",
            "VENZA",
            "YARIS",
        ],
        "VOLKSWAGEN": [
            "ALL MODELS",
            "ATLAS",
            "BEETLE",
            "GOLF",
            "JETTA",
            "PASSAT",
            "TAOS SE",
            "TIGUAN",
        ],
        "VOLVO": ["ALL MODELS", "S60", "S90", "XC40", "XC60", "XC90"],
    },
    "year_buttons": ["2016 - 2020", "2021 - 2023", "2024 - 2025"],
    "odometer_buttons": [
        "0 - 30 тыс. км",
        "30 - 50 тыс. км",
        "50 - 80 тыс. км",
        "Не имеет значения",
    ],
    "auction_status_buttons": [
        "Только BUY NOW",
        "Все варианты",
    ],
    "body_style_buttons": [
        "Седан",
        "Кроссовер",
        "Электромобиль",
    ],
    "budget_buttons": [
        "до 12.000$",
        "12.000$ - 15.000$",
        "15.000$ - 20.000$",
        "20.000$ - 30.000$",
        "30.000$ - 50.000$",
        "50.000$+",
    ],
}


LEXICON_RU_CSV: dict[str, Callable[[Any], str]] = {
    "2016 - 2020": [2016, 2017, 2018, 2019, 2020],
    "2021 - 2023": [2021, 2023],
    "2024 - 2025": [2024, 2025],
    "Не имеет значения": None,
    "0 - 30 тыс. км": [0, 18642],
    "30 - 50 тыс. км": [18643, 31069],
    "50 - 80 тыс. км": [31070, 49710],
    "Все варианты": False,
    "Только BUY NOW": True,
    "Седан": "Sedan",
    "Кроссовер": "SUV",
    "Электромобиль": "Electric",
    "до 12.000$": [0, 12000],
    "12.000$ - 15.000$": [12000, 15000],
    "15.000$ - 20.000$": [15000, 20000],
    "20.000$ - 30.000$": [20000, 30000],
    "30.000$ - 50.000$": [30000, 50000],
    "50.000$+": [50000, 999999],
}


LEXICON_EN_RU: dict[str, dict[str, str]] = {
    "Color": {
        "CHARCOAL": "Серый",
        "BLUE": "Синий",
        "ORANGE": "Оранжевый",
        "SILVER": "Серебристый",
        "GRAY": "Серый",
        "WHITE": "Белый",
        "BEIGE": "Бежевый",
        "BLACK": "Черный",
        "RED": "Красный",
        "BURGUNDY": "Бордовый",
        "TWO TONE": "Комбинированный",
        "YELLOW": "Желтый",
        "BURN": "Оранжевый",
        "GREEN": "Зеленый",
        "TURQUOISE": "Бирюзовый",
        "GOLD": "Золотистый",
        "TAN": "Коричневый",
        "PURPLE": "Фиолетовый",
        "MAROON": "Бордовый",
        "TEAL": "Бирюзовый",
        "BROWN": "Коричневый",
        "CREAM": "Бежевый",
        "UNKNOWN - NOT OK FOR INV.": "Не указан",
        "PINK": "Розовый",
    },
    "Drive": {
        "Front-wheel Drive": "Передний",
        "Rear-wheel drive": "Задний",
        "4x4 w/Rear Wheel Drv": "Полный",
        "All wheel drive": "Полный",
        "4x4 w/Front Whl Drv": "Полный",
        "Four by Four": "Полный",
    },
    "Transmission": {"AUTOMATIC": "АКПП", "MANUAL": "МКПП"},
}


LEXICON_ASSISTED_GALLERY_RU: dict[str, Callable[..., str]] = {
    "caption": lambda name, car_title, body_label, budget_label: (
        f"{name}, вот пример из категории «{body_label}» в бюджете «{budget_label}».\n\n"
        f"<b>{car_title}</b> — ориентир по типу и классу автомобиля. Реальные лоты на аукционе "
        f"мы подбираем индивидуально под ваш запрос и рассчитываем итоговую стоимость «под ключ»."
    ),
}


LEXICON_CAPTION_RU: dict[str, Callable[[Any], str] | str] = {
    "caption_text": lambda name, number, year, brand, model, color, odometer, engine, drive, transmission, sale_date: (
        f"{name}, на данный момент доступны следующие варианты:\r\n"
        f"<b>Автомобиль № {number}</b>\r\n"
        f"<b>{brand} {model}</b> 🔥\r\n\n"
        f"✅ Модельный год: {year}\r\n"
        f"✅ Цвет: {color}\r\n"
        f"✅ Объем двигателя: {engine[:4]}\r\n"
        f"✅ Трансмиссия: {transmission}\r\n"
        f"✅ Привод: {drive}\r\n"
        f"✅ Пробег: {int(float(odometer) * 1.60934)} км.\r\n"
        f"⌛ Дата аукциона: "
        f"{'Не назначена' if sale_date == '0' else sale_date[0:4] + '-' + sale_date[4:6] + '-' + sale_date[6:]}"
    )
}

LEXICON_NEWSLETTER_RU: dict[str, str] = {
    "car_selection_text": "Вы можете выбрать понравившийся автомобиль и мы оперативно изучим данный лот🔥 на аукционе и свяжемся с Вами и предоставим всю информацию с расчетом финальной цены в РБ!"
}

LEXICON_PROMO_RU: dict[str, str] = {
    "48h_promo_text": 'Присоединяйтесь к нашему Telegram-каналу "Авто из США". Не упусти возможность заказать лучший автомобиль🔥\n\n'
    "✅ Только актуальные предложения авто с аукционов.\n"
    "✅ Ежедневное обновление.\n"
    "✅ Реальные авто с ценами в РБ.",
    "telegram_button_text": "Перейти в Telegram-аккаунт",
    "10m_inactivity_text": 'Подписывайся на наш Instagram, в котором мы ежедневно публикуем авто, выигранные для наших клиентов, а так же самые выгодные варианты с аукционов. Будь вкурсе всех самых "ГОРЯЧИХ" предложений.',
    "instagram_button_text": "Перейти в Instagram",
    "24h_consultation_text": "Не можете определиться с авто? Оставьте свой номер телефона и наши менеджеры подберут варианты под Ваш бюджет абсолютно БЕСПЛАТНО!\n\n"
    "Компания AmericaTreade предоставляет полный\n"
    "комплекс услуг по подбору авто из США с\n"
    "реальной денежной выгодой до 40% от\n"
    "авторынка РБ.\n\n"
    "• Без первого взноса. Начинаем подбор авто\n"
    "сразу после заключения договора.\n\n"
    "• Полное сопровождение. Менеджер будет с Вами\n"
    "на связи вплоть до постановки авто на учет.\n\n"
    "• Оплата через банк. Все платежи осуществляются\n"
    "исключительно через банк, никаких наличных и\n"
    "подозрительных переводов",
    "consultation_button_text": "Оставить заявку на бесплатный подбор",
}
