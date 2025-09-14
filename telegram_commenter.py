#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import os
import random
import sqlite3
from datetime import datetime
from typing import Dict, List
from langdetect import detect
import g4f
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import Channel, MessageService
from telethon.tl.functions.messages import SendReactionRequest, GetDiscussionMessageRequest
from telethon.tl.types import ReactionEmoji

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TelegramCommenter:
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.clients: Dict[str, TelegramClient] = {}
        self.active_tasks = []
        self.db_path = "commenter.db"
        self.monitoring_active = False
        self.init_database()
        self.channel_entities = {}

    def load_config(self) -> dict:
        STANDARD_STICKERS = [
            "CAACAgIAAxkBAAECYlBhvkxeAAGqrFgAAc9wAwABr2oWyZwAAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYlJhvkxgAAHJg0cAAYQBgAACgp2TGwABHgACDAEAAladvQpZmaIB6S-q5SAE",
            "CAACAgIAAxkBAAECYlRhvkxiAAGFBwABNAABrE8AAc7WA4oAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYlZhvkxkAAF2BgABQQABcAACgZ_AAIUAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYlhhvkxmAAGsAAH-AAGA_wACEwACv0qBAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYlphvkxoAAHZBwABtgABBAAC5t-qD8gAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYlxhvkxqAAFmAwAB6wABQgACjU1NBAAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYl5hvkxsAAFCBwABYAABcAACEbUAAYkAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYmBhvkxuAAFmAwABeAABwAACs8ADAAUAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
            "CAACAgIAAxkBAAECYmJhvkxwAAGtBAABYwABqgACOgABF7oAAR4AAgwBAAJWnb0KWZmiAAHpL6rlIAQ",
        ]

        default_config = {
            "accounts": [],
            "channels": [],
            "comment_settings": {
                "min_delay": 1,
                "max_delay": 180,
                "comment_probability": 0.7,
                "like_probability": 0.8,
                "reply_like_probability": 0.3,
                "silent_activity_probability": 0.2,
                "min_comments_per_post": 3,
                "max_comments_per_post": 8,
                "styles": ["short", "long", "emotional", "neutral", "question", "personal"]
            },
            "sticker_settings": {
                "enabled": True,
                "probability": 0.15,
                "use_standard_stickers": True,
                "standard_stickers": STANDARD_STICKERS,
                "custom_stickers": []
            },
            "ai_settings": {
                "enabled": True,
                "model": "gpt-4o-mini",
                "max_length": 150
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    for ch in config.get("channels", []):
                        if "accounts" not in ch:
                            ch["accounts"] = []
                    merged_config = {**default_config, **config}
                    if "sticker_settings" not in merged_config:
                        merged_config["sticker_settings"] = default_config["sticker_settings"]
                    else:
                        for key, value in default_config["sticker_settings"].items():
                            if key not in merged_config["sticker_settings"]:
                                merged_config["sticker_settings"][key] = value
                    return merged_config
            except Exception as e:
                logger.warning(f"Помилка завантаження конфігурації: {e}, використовуємо стандартну")
        
        return default_config
    
    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT,
                channel TEXT,
                action TEXT,
                message_id INTEGER,
                timestamp DATETIME,
                content TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                message_id INTEGER,
                channel TEXT,
                account TEXT,
                processed_at DATETIME,
                PRIMARY KEY (message_id, channel, account)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_activity(self, account: str, channel: str, action: str, message_id: int = None, content: str = ""):
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO activity_log (account, channel, action, message_id, timestamp, content)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (account, channel, action, message_id, datetime.now(), content))
        conn.commit()
        conn.close()
        logger.info(f"[{account}] {action} у {channel}: {content[:50]}...")
    
    def is_post_processed(self, message_id: int, channel: str, account: str) -> bool:
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM processed_posts WHERE message_id=? AND channel=? AND account=?', 
                      (message_id, channel, account))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def mark_post_processed(self, message_id: int, channel: str, account: str):
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO processed_posts VALUES (?, ?, ?, ?)', 
                      (message_id, channel, account, datetime.now()))
        conn.commit()
        conn.close()
    
    def get_random_accounts_for_channel(self, channel_username: str, available_accounts: List[str]) -> List[str]:
        settings = self.config["comment_settings"]
        min_comments = settings["min_comments_per_post"]
        max_comments = settings["max_comments_per_post"]
        
        max_possible = min(len(available_accounts), max_comments)
        min_possible = min(min_comments, max_possible)
        
        if min_possible <= 0:
            return []
        
        num_accounts = random.randint(min_possible, max_possible)
        return random.sample(available_accounts, num_accounts)

    async def ask_gpt4free(self, prompt: str) -> str:
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: g4f.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
            )
            return response if response else ""
        except Exception as e:
            logger.debug(f"Помилка запиту GPT: {e}")
            return ""
    
    async def generate_comment(self, post_text: str, style: str = "neutral", lang: str = "uk") -> str:
        if not self.config["ai_settings"]["enabled"]:
            return self.get_fallback_comment(style, lang)
        
        post_topic = self.analyze_post_topic(post_text, lang)
        
        live_additions = {
            "uk": [
                "Використовуй сленг: четко, о як, зашибись, бро, го, щас, движуха, в деле, кайф, огонь",
                "Будь живим як в чаті з друзями. Коротко і по справі",
                "Стиль молодіжний, без формальності. Можна матюки замінити на м'які варіанти"
            ],
            "ru": [
                "Используй сленг: четко, о как, зашибись, бро, го, щас, движуха, в деле, кайф, огонь", 
                "Будь живым как в чате с друзьями. Коротко и по делу",
                "Стиль молодежный, без формальности. Можно маты заменить на мягкие варианты"
            ],
            "en": [
                "Use crypto slang: LFG, HODL, moon, FOMO, based, chad, YOLO, WAGMI, bullish, rekt",
                "Be alive like chatting with friends. Short and direct",
                "Youth style, no formality. Crypto community vibes"
            ]
        }
        
        topic_crypto_terms = self.get_topic_crypto_terms(post_topic, lang)
        
        lang_prompts = {
            "uk": {
                "short": f"Напиши короткий коментар (1-3 слова) українською ПРО ТЕМУ: {post_topic}. Живий сленг як четко, о як, зашибись, го, кайф. Пост: {post_text[:100]}. Відповідь має СТОСУВАТИСЯ теми поста. Тільки текст.",
                "long": f"Напиши живий коментар (1-2 речення) українською ПРО: {post_topic}. Стиль чату з друзями: бро, движуха, в деле, щас. Використай релевантні крипто-терміни для цієї теми. Пост: {post_text[:200]}. ОБОВ'ЯЗКОВО зв'яжи з темою поста. Тільки текст.",
                "emotional": f"Напиши емоційний коментар українською з емодзі ПРО: {post_topic}. Стиль: огонь, зашибись, кайф! + релевантні крипто терміни. Пост: {post_text[:150]}. Коментар має відображати емоцію щодо конкретної теми. Тільки текст.",
                "neutral": f"Напиши коментар українською ПРО ТЕМУ: {post_topic}. Живий стиль + релевантні терміни для цієї теми. Коротко як в чаті але по суті поста. Пост: {post_text[:200]}. Тільки текст.",
                "question": f"Задай коротке питання українською ПРО: {post_topic}. Стиль чату: че там, як справи + терміни з цієї теми. Пост: {post_text[:150]}. Питання має стосуватися конкретної теми поста. Тільки питання.",
                "personal": f"Напиши особистий коментар українською ПРО: {post_topic}. Стиль: сам пробував, був досвід + сленг з цієї теми. Пост: {post_text[:200]}. Розкажи свій досвід з цієї конкретної теми. Тільки текст."
            },
            "ru": {
                "short": f"Напиши короткий коммент (1-3 слова) на русском ПРО ТЕМУ: {post_topic}. Живой сленг как четко, о как, зашибись, го, кайф. Пост: {post_text[:100]}. Ответ должен КАСАТЬСЯ темы поста. Только текст.",
                "long": f"Напиши живой коммент (1-2 предложения) на русском ПРО: {post_topic}. Стиль чата с друзьями: бро, движуха, в деле, щас. Используй релевантные крипто-термины для этой темы. Пост: {post_text[:200]}. ОБЯЗАТЕЛЬНО свяжи с темой поста. Только текст.",
                "emotional": f"Напиши эмоциональный коммент на русском с эмодзи ПРО: {post_topic}. Стиль: огонь, зашибись, кайф! + релевантные крипто термины. Пост: {post_text[:150]}. Коммент должен отражать эмоцию по конкретной теме. Только текст.",
                "neutral": f"Напиши коммент на русском ПРО ТЕМУ: {post_topic}. Живой стиль + релевантные термины для этой темы. Коротко как в чате но по сути поста. Пост: {post_text[:200]}. Только текст.",
                "question": f"Задай короткий вопрос на русском ПРО: {post_topic}. Стиль чата: че там, как дела + термины из этой темы. Пост: {post_text[:150]}. Вопрос должен касаться конкретной темы поста. Только вопрос.",
                "personal": f"Напиши личный коммент на русском ПРО: {post_topic}. Стиль: сам пробовал, был опыт + сленг из этой темы. Пост: {post_text[:200]}. Расскажи свой опыт с этой конкретной темой. Только текст."
            },
            "en": {
                "short": f"Write short comment (1-3 words) in English ABOUT: {post_topic}. Live slang like LFG, based, chad, YOLO. Post: {post_text[:100]}. Response must RELATE to post topic. Text only.",
                "long": f"Write live comment (1-2 sentences) in English ABOUT: {post_topic}. Chat style with friends: bro, movement, let's go. Add relevant crypto slang for this topic. Post: {post_text[:200]}. MUST connect to post topic. Text only.",  
                "emotional": f"Write emotional comment in English with emoji ABOUT: {post_topic}. Style: fire, awesome, sick! + relevant crypto slang. Post: {post_text[:150]}. Comment should reflect emotion about specific topic. Text only.",
                "neutral": f"Write comment in English ABOUT TOPIC: {post_topic}. Live style + relevant terms for this topic. Short like in chat but on point about post. Post: {post_text[:200]}. Text only.",
                "question": f"Ask short question in English ABOUT: {post_topic}. Chat style: what's up, how's it + terms from this topic. Post: {post_text[:150]}. Question must relate to specific post topic. Question only.",
                "personal": f"Write personal comment in English ABOUT: {post_topic}. Style: tried it myself, had experience + slang from this topic. Post: {post_text[:200]}. Share your experience with this specific topic. Text only."
            }
        }
        
        base_prompt = lang_prompts.get(lang, lang_prompts["uk"]).get(style, lang_prompts["uk"]["neutral"])
        
        if random.random() < 0.6:
            live_addition = random.choice(live_additions.get(lang, live_additions["uk"]))
            full_prompt = f"{base_prompt} {live_addition}"
        else:
            topic_terms = ', '.join(topic_crypto_terms[:5])
            full_prompt = f"{base_prompt} Використай терміни: {topic_terms}"
        
        comment = await self.ask_gpt4free(full_prompt)
        if not comment:
            return self.get_fallback_comment(style, lang, post_topic)
        
        comment = comment.strip().strip('"').strip("'")
        
        return comment[:self.config["ai_settings"]["max_length"]]

    def analyze_post_topic(self, post_text: str, lang: str) -> str:
        post_lower = post_text.lower()
        
        crypto_topics = {
            "bitcoin": ["bitcoin", "btc", "биткоин", "біткоїн"],
            "ethereum": ["ethereum", "eth", "эфир", "ефір", "vitalik"],
            "altcoins": ["altcoin", "альткоин", "альткойн", "shitcoin", "gem"],
            "defi": ["defi", "decentralized", "uniswap", "compound", "aave", "liquidity", "farming", "yield"],
            "nft": ["nft", "opensea", "collectible", "коллекция", "collection", "mint"],
            "trading": ["trade", "trading", "pump", "dump", "chart", "candle", "resistance", "support"],
            "staking": ["staking", "stake", "validator", "pos", "proof", "reward"],
            "mining": ["mining", "miner", "hash", "pool", "asic", "gpu"],
            "regulation": ["regulation", "sec", "law", "government", "ban", "legal"],
            "market": ["market", "bull", "bear", "crash", "moon", "ath", "dip", "correction"],
            "tech": ["blockchain", "smart contract", "layer", "consensus", "node", "fork"],
            "news": ["news", "announcement", "update", "partnership", "integration"]
        }
        
        detected_topics = []
        for topic, keywords in crypto_topics.items():
            for keyword in keywords:
                if keyword in post_lower:
                    detected_topics.append(topic)
                    break
        
        if detected_topics:
            return detected_topics[0]
        
        if any(word in post_lower for word in ["price", "цена", "ціна", "cost", "expensive", "cheap"]):
            return "market"
        elif any(word in post_lower for word in ["new", "новый", "новий", "launch", "release"]):
            return "news"
        elif any(word in post_lower for word in ["how", "как", "що", "tutorial", "guide"]):
            return "tech"
        else:
            return "general"

    def get_topic_crypto_terms(self, topic: str, lang: str) -> list:
        topic_terms = {
            "bitcoin": {
                "uk": ["HODL", "BTC", "satoshi", "Lightning Network", "халвінг", "цифрове золото", "peer-to-peer", "21M supply"],
                "ru": ["HODL", "BTC", "satoshi", "Lightning Network", "халвинг", "цифровое золото", "peer-to-peer", "21M supply"],
                "en": ["HODL", "BTC", "satoshi", "Lightning Network", "halving", "digital gold", "peer-to-peer", "21M supply"]
            },
            "ethereum": {
                "uk": ["ETH", "gas fees", "EIP", "smart contracts", "DApps", "Web3", "Vitalik", "merge", "шардинг"],
                "ru": ["ETH", "gas fees", "EIP", "smart contracts", "DApps", "Web3", "Vitalik", "merge", "шардинг"],
                "en": ["ETH", "gas fees", "EIP", "smart contracts", "DApps", "Web3", "Vitalik", "merge", "sharding"]
            },
            "defi": {
                "uk": ["DeFi", "yield farming", "liquidity pool", "AMM", "DEX", "TVL", "impermanent loss", "governance token"],
                "ru": ["DeFi", "yield farming", "liquidity pool", "AMM", "DEX", "TVL", "impermanent loss", "governance token"],
                "en": ["DeFi", "yield farming", "liquidity pool", "AMM", "DEX", "TVL", "impermanent loss", "governance token"]
            },
            "nft": {
                "uk": ["NFT", "mint", "floor price", "royalties", "metadata", "IPFS", "utility", "blue chip"],
                "ru": ["NFT", "mint", "floor price", "royalties", "metadata", "IPFS", "utility", "blue chip"],
                "en": ["NFT", "mint", "floor price", "royalties", "metadata", "IPFS", "utility", "blue chip"]
            },
            "trading": {
                "uk": ["TA", "RSI", "MACD", "support", "resistance", "breakout", "volume", "FOMO", "FUD"],
                "ru": ["TA", "RSI", "MACD", "support", "resistance", "breakout", "volume", "FOMO", "FUD"],
                "en": ["TA", "RSI", "MACD", "support", "resistance", "breakout", "volume", "FOMO", "FUD"]
            },
            "market": {
                "uk": ["bull run", "bear market", "ATH", "ATL", "market cap", "whale", "diamond hands", "paper hands"],
                "ru": ["bull run", "bear market", "ATH", "ATL", "market cap", "whale", "diamond hands", "paper hands"],
                "en": ["bull run", "bear market", "ATH", "ATL", "market cap", "whale", "diamond hands", "paper hands"]
            },
            "staking": {
                "uk": ["staking", "validator", "APY", "slash", "unstaking", "delegation", "consensus", "PoS"],
                "ru": ["staking", "validator", "APY", "slash", "unstaking", "delegation", "consensus", "PoS"],
                "en": ["staking", "validator", "APY", "slash", "unstaking", "delegation", "consensus", "PoS"]
            }
        }
        
        return topic_terms.get(topic, {}).get(lang, [
            "HODL", "FOMO", "FUD", "moon", "whale", "gem", "DYOR", "diamond hands", "LFG", "WAGMI"
        ])

    def get_fallback_comment(self, style: str, lang: str, topic: str = "general") -> str:
        topic_comments = {
            "bitcoin": {
                "uk": {
                    "short": ["HODL!", "BTC до moon!", "Сатоши!", "Digital gold!", "₿"],
                    "long": ["BTC - це майбутнє, бро! HODL до lambo 🚗", "Сатоши знав що робив. Цифрове золото назавжди!", "Lightning Network топ! Швидко і дешево"],
                    "question": ["21 мільйон і все? Дефіцит топ чи що?", "Халвінг коли? Bull run підготували?"]
                },
                "en": {
                    "short": ["HODL!", "BTC moon!", "Satoshi!", "Digital gold!", "₿"],
                    "long": ["BTC is the future, bro! HODL to lambo 🚗", "Satoshi knew what's up. Digital gold forever!", "Lightning Network rocks! Fast and cheap"],
                    "question": ["21 million cap? Scarcity bullish or what?", "Halving when? Bull run prepared?"]
                }
            },
            "ethereum": {
                "uk": {
                    "short": ["ETH!", "Vitalik top!", "Web3!", "Smart contracts!"],
                    "long": ["ETH екосистема неймовірна! DApps майбутнє 🌐", "Gas fees жесть, але технологія космос!", "Smart contracts революція справжня"],
                    "question": ["Gas fees коли нормальні? Layer 2 рятує?", "Шардинг коли? Скейлинг потрібний"]
                }
            },
            "defi": {
                "uk": {
                    "short": ["DeFi!", "Yield!", "APY космос!", "No banks!"],
                    "long": ["DeFi революція! Банки не потрібні більше 🏦", "Yield farming ризикований але прибутковий", "Liquidity mining топова стратегія"],
                    "question": ["Impermanent loss великий? Ризик варто?", "TVL зростає? Протокол надійний?"]
                }
            }
        }
        
        if topic in topic_comments:
            topic_data = topic_comments[topic].get(lang, topic_comments[topic].get("en", {}))
            if style in topic_data:
                return random.choice(topic_data[style])
        
        comments = {
            "uk": {
                "short": [
                    "Четко!", "О як!", "Зашибись!", "Бро!", "Го!", "Щас!", 
                    "HODL!", "Moon!", "LFG!", "Че там?", "Погнали!", 
                    "Движуха!", "На весь сайз!", "В деле!", "Кайф!", 
                    "Огонь!", "Топчик!", "Круто!", "Жесть!", "Базара нет!"
                ],
                "long": [
                    "Четко подано, бро! HODL стратегія топ 💎",
                    "О як розповів! На весь сайз залітаю в цю тему",
                    "Зашибись аналіз! Че там за движуха з китами?", 
                    "Погнали, я в деле! FOMO рівень максимум 🚀",
                    "Щас буде памп? Whale alert чи що?",
                    "Бро, це gem! DYOR завжди, але виглядає bullish",
                    "Движуха серйозна! Diamond hands тримають позиції",
                    "На весь сайз заходжу! APY космічний просто",
                    "Го разом farmити! Liquidity pool виглядає сочно"
                ],
                "emotional": [
                    "Вау, зашибись! 🔥 TO THE MOON baby!",
                    "О як! 🚀 Це moonshot чи що?!",
                    "Четко! 💎 Diamond hands forever!",
                    "Жесть яка! 🌙 HODL до останнього!",
                    "Огонь! ⚡ Whale move такий потужний!",
                    "Бро, це космос! 🪐 ATH буде скоро!",
                    "Кайф! 🎯 Bullish настрій зашкалює!"
                ],
                "neutral": [
                    "Цікава інфа. BTC тренд як?",
                    "Корисно. ETH staking оновлення є?",
                    "Актуально. DeFi протокол надійний?",
                    "DYOR зробив, виглядає ок",
                    "Che там з gas fees? Нормально?",
                    "Tokenomics як? Supply скільки?",
                    "Liquidity достатня чи тонко?",
                    "Chart що показує? RSI рівні?",
                    "Market cap нормальний? Не overvalued?"
                ],
                "question": [
                    "Che там за hype? FOMO чи реальний gem?",
                    "Whale movements є? Великі transferи бачили?",
                    "APY реальний чи unsustainable? Як думаєте?",
                    "Rugpull ризик є? Contract audit проходив?",
                    "Staking pool безпечний? Lock period який?",
                    "IDO коли? Whitelist ще можна потрапити?",
                    "Bear trap чи справжній dump? Технічний аналіз?",
                    "Cross-chain bridge працює стабільно?",
                    "DAO governance активна? Community strong?"
                ],
                "personal": [
                    "Був схожий досвід. HODLив ETH з 2020",
                    "Згоден на всі 100! FOMO вдарив серйозно",
                    "Моя думка: DYOR + diamond hands = profit",
                    "Сам farmлю вже пів року. APY падає але ок",
                    "В цю тему заходив раніше. Whale alerts спрацювали",
                    "Paper hands був колись, тепер тільки HODL",
                    "Bag holder цього токена. Чекаю moon shot",
                    "DCA стратегія працює. Buy the dip завжди",
                    "NFT flip досвід є. Blue chip тільки беру"
                ]
            },
            "ru": {
                "short": [
                    "Четко!", "О как!", "Зашибись!", "Бро!", "Го!", "Щас!", 
                    "HODL!", "Moon!", "LFG!", "Че там?", "Погнали!", 
                    "Движуха!", "На весь сайз!", "В деле!", "Кайф!", 
                    "Огонь!", "Топчик!", "Круто!", "Жесть!", "Базара нет!"
                ],
                "long": [
                    "Четко подано, бро! HODL стратегия топ 💎",
                    "О как рассказал! На весь сайз залетаю в эту тему",
                    "Зашибись анализ! Че там за движуха с китами?", 
                    "Погнали, я в деле! FOMO уровень максимум 🚀",
                    "Щас будет памп? Whale alert или что?",
                    "Бро, это gem! DYOR всегда, но выглядит bullish",
                    "Движуха серьезная! Diamond hands держат позиции",
                    "На весь сайз захожу! APY космический просто",
                    "Го вместе фармить! Liquidity pool выглядит сочно"
                ],
                "emotional": [
                    "Вау, зашибись! 🔥 TO THE MOON baby!",
                    "О как! 🚀 Это moonshot или что?!",
                    "Четко! 💎 Diamond hands forever!",
                    "Жесть какая! 🌙 HODL до последнего!",
                    "Огонь! ⚡ Whale move такой мощный!",
                    "Бро, это космос! 🪐 ATH будет скоро!",
                    "Кайф! 🎯 Bullish настрой зашкаливает!"
                ],
                "neutral": [
                    "Интересная инфа. BTC тренд как?",
                    "Полезно. ETH staking обновления есть?",
                    "Актуально. DeFi протокол надежный?",
                    "DYOR сделал, выглядит ок",
                    "Че там с gas fees? Нормально?",
                    "Tokenomics как? Supply сколько?",
                    "Liquidity достаточная или тонко?",
                    "Chart что показывает? RSI уровни?",
                    "Market cap нормальный? Не overvalued?"
                ],
                "question": [
                    "Че там за hype? FOMO или реальный gem?",
                    "Whale movements есть? Большие transferы видели?",
                    "APY реальный или unsustainable? Как думаете?",
                    "Rugpull риск есть? Contract audit проходил?",
                    "Staking pool безопасный? Lock period какой?",
                    "IDO когда? Whitelist еще можно попасть?",
                    "Bear trap или настоящий dump? Технический анализ?",
                    "Cross-chain bridge работает стабильно?",
                    "DAO governance активная? Community strong?"
                ],
                "personal": [
                    "Был похожий опыт. HODLил ETH с 2020",
                    "Согласен на все 100! FOMO ударил серьезно",
                    "Мое мнение: DYOR + diamond hands = profit",
                    "Сам фармлю уже полгода. APY падает но ок",
                    "В эту тему заходил раньше. Whale alerts сработали",
                    "Paper hands был когда-то, теперь только HODL",
                    "Bag holder этого токена. Жду moon shot",
                    "DCA стратегия работает. Buy the dip всегда",
                    "NFT flip опыт есть. Blue chip только беру"
                ]
            },
            "en": {
                "short": [
                    "LFG!", "HODL!", "Moon!", "Bullish!", "Based!", "Chad move!",
                    "Diamond hands!", "YOLO!", "BTFD!", "Rekt!", "FOMO!", "Shill!",
                    "Whale alert!", "Pump it!", "To the moon!", "Stonks!", "NGMI!", "WAGMI!"
                ],
                "long": [
                    "LFG! This looks like a moonshot opportunity 🚀",
                    "HODL strategy looking solid. Diamond hands only 💎",
                    "Bullish setup here! Whale movements confirmed",
                    "FOMO kicking in hard. DYOR but looks promising",
                    "Chad analysis! APY numbers are astronomical",
                    "Pump incoming? Chart patterns screaming bullish",
                    "DeFi farming opportunity? Liquidity looks thick",
                    "YOLO mode activated! Risk/reward ratio insane",
                    "Based take! Community sentiment through the roof"
                ],
                "emotional": [
                    "Holy shit! 🔥 TO THE MOON we go!",
                    "WAGMI! 🚀 This is the moonshot we needed!",
                    "Diamond hands forever! 💎 Never selling!",
                    "LFG! 🌙 HODL until Valhalla!",
                    "Bullish AF! ⚡ Whale moves confirmed!",
                    "Based! 🪐 ATH incoming soon!",
                    "FOMO! 🎯 Bull run starting now!"
                ],
                "neutral": [
                    "Interesting data. BTC correlation?",
                    "Useful info. ETH merge impact?",
                    "Relevant. Protocol security audit?",
                    "DYOR completed, looks decent",
                    "Gas fees situation? Manageable?",
                    "Tokenomics solid? Max supply?",
                    "Liquidity sufficient? Slippage low?",
                    "Technical analysis? Support levels?",
                    "Market cap reasonable? Not overvalued?"
                ],
                "question": [
                    "Real gem or just hype? FOMO trap?",
                    "Whale activity confirmed? Large transfers?",
                    "Sustainable APY or too good to be true?",
                    "Rug risk assessment? Contract verified?",
                    "Staking rewards legit? Lock period?",
                    "IDO access available? Whitelist open?",
                    "Bear trap or genuine correction? TA?",
                    "Cross-chain functionality working?",
                    "DAO participation active? Strong community?"
                ],
                "personal": [
                    "Been there! HODLed ETH since 2020",
                    "100% agree! FOMO hit me hard too",
                    "My take: DYOR + diamond hands = win",
                    "Farming this for months. APY dropping but ok",
                    "Played this before. Whale alerts worked",
                    "Was paper hands once, now HODL only",
                    "Bag holding this token. Waiting moon shot",
                    "DCA strategy works. Always buy dips",
                    "NFT flipping experience. Blue chips only"
                ]
            }
        }

        if style == "short":
            if random.random() < 0.7:
                live_phrases = {
                    "uk": ["Четко!", "О як!", "Зашибись!", "Го!", "В деле!", "Движуха!", "Кайф!", "Огонь!"],
                    "ru": ["Четко!", "О как!", "Зашибись!", "Го!", "В деле!", "Движуха!", "Кайф!", "Огонь!"],
                    "en": ["LFG!", "Based!", "Chad move!", "YOLO!", "Moon!", "Bullish!", "WAGMI!"]
                }
                return random.choice(live_phrases.get(lang, live_phrases["en"]))
        
        return random.choice(comments.get(lang, comments["uk"]).get(style, comments["uk"]["neutral"]))
    
    def get_weighted_style(self):
        styles = self.config["comment_settings"]["styles"]
        weights = [3 if s == "short" else 1 if s == "long" else 2 for s in styles]
        return random.choices(styles, weights=weights, k=1)[0]
    
    def detect_language(self, text: str) -> str:
        try:
            lang = detect(text)
            if lang in ["uk", "ru", "en"]:
                return lang
            return "uk"
        except:
            return "uk"
    
    def add_account(self, phone: str, api_id: str, api_hash: str, name: str = "") -> bool:
        account = {
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "name": name or phone,
            "active": True,
            "session_file": f"session_{phone}"
        }
        
        if not any(acc["phone"] == phone for acc in self.config["accounts"]):
            self.config["accounts"].append(account)
            self.save_config()
            logger.info(f"Обліковий запис {phone} додано")
            return True
        return False
    
    def remove_account(self, phone: str) -> bool:
        initial_count = len(self.config["accounts"])
        self.config["accounts"] = [acc for acc in self.config["accounts"] if acc["phone"] != phone]
        
        for ch in self.config["channels"]:
            if phone in ch.get("accounts", []):
                ch["accounts"].remove(phone)
        
        if len(self.config["accounts"]) < initial_count:
            session_file = f"sessions/session_{phone}.session"
            if os.path.exists(session_file):
                os.remove(session_file)
            
            self.save_config()
            logger.info(f"Обліковий запис {phone} видалено")
            return True
        return False
    
    def add_channel(self, channel_username: str, assigned_accounts: List[str] = None, enabled: bool = True) -> bool:
        channel_username = channel_username.replace("@", "").replace("https://t.me/", "")
        
        if any(ch["username"] == channel_username for ch in self.config["channels"]):
            return False
        
        self.config["channels"].append({
            "username": channel_username,
            "enabled": enabled,
            "accounts": assigned_accounts or [],
            "last_message_id": 0
        })
        self.save_config()
        logger.info(f"Канал @{channel_username} додано з обліковими записами {assigned_accounts}")
        return True
    
    def assign_accounts_to_channel(self, channel_username: str, assigned_accounts: List[str]) -> bool:
        channel_username = channel_username.replace("@", "")
        channel_config = next((ch for ch in self.config["channels"] if ch["username"] == channel_username), None)
        if not channel_config:
            return False
        
        valid_accounts = [acc["phone"] for acc in self.config["accounts"]]
        channel_config["accounts"] = [phone for phone in assigned_accounts if phone in valid_accounts]
        self.save_config()
        logger.info(f"Призначено {channel_config['accounts']} до @{channel_username}")
        return True
    
    def remove_channel(self, channel_username: str) -> bool:
        channel_username = channel_username.replace("@", "")
        initial_count = len(self.config["channels"])
        self.config["channels"] = [ch for ch in self.config["channels"] if ch["username"] != channel_username]
        
        if len(self.config["channels"]) < initial_count:
            self.save_config()
            logger.info(f"Канал @{channel_username} видалено")
            return True
        return False
    
    async def create_client(self, account, input_callback, log_callback):
        phone = account["phone"]
        api_id = account["api_id"]
        api_hash = account["api_hash"]
        client = None
        try:
            os.makedirs('sessions', exist_ok=True)
            
            client = TelegramClient(f'sessions/{phone}', api_id, api_hash)
            await client.connect()
            
            if not await client.is_user_authorized():
                if not input_callback:
                    log_callback(f"⚠️ Потрібна авторизація для {phone}, пропущено")
                    return None
                log_callback(f"🔐 Потрібна авторизація для {phone}")
                
                await client.send_code_request(phone)
                
                code = input_callback(
                    "Код авторизації",
                    f"Введіть код Telegram для {phone}:"
                )
                
                if not code:
                    log_callback(f"❌ Код не введено для {phone}")
                    return None
                
                try:
                    await client.sign_in(phone, code)
                    log_callback(f"✅ Авторизовано {phone}")
                except SessionPasswordNeededError:
                    password = input_callback(
                        "Пароль 2FA",
                        f"Введіть пароль 2FA для {phone}:",
                        show_char='*'
                    )
                    
                    if not password:
                        log_callback(f"❌ Пароль не введено для {phone}")
                        return None
                    
                    await client.sign_in(password=password)
                    log_callback(f"✅ Авторизовано з 2FA для {phone}")
                except Exception as e:
                    log_callback(f"❌ Помилка авторизації для {phone}: {e}")
                    return None
            else:
                log_callback(f"✅ {phone} уже авторизовано")
            
            return client
        except Exception as e:
            log_callback(f"❌ Помилка створення клієнта для {phone}: {e}")
            return None
    
    async def check_connections_gui(self, log_callback) -> str:
        log_callback("🔍 Перевірка підключень облікових записів...")
        results = []
        for account in self.config["accounts"]:
            if not account["active"]:
                results.append(f"{account['name']} ({account['phone']}): Неактивний")
                continue
            
            client = await self.create_client(account, None, log_callback)
            if client:
                try:
                    if await client.is_user_authorized():
                        results.append(f"{account['name']} ({account['phone']}): ✅ Активний")
                    else:
                        results.append(f"{account['name']} ({account['phone']}): ⚠️ Потрібна авторизація")
                except Exception as e:
                    results.append(f"{account['name']} ({account['phone']}): ❌ Заблоковано/Помилка: {e}")
                finally:
                    await client.disconnect()
            else:
                results.append(f"{account['name']} ({account['phone']}): ❌ Помилка підключення")
        
        return "Результати перевірки підключення:\n" + "\n".join(results)
    
    async def initialize_clients_gui(self, input_callback, log_callback):
        log_callback("🔍 Перевірка авторизації облікових записів...")
        
        accounts_to_auth = []
        for account in self.config["accounts"]:
            if not account["active"]:
                log_callback(f"⏭️ Пропущено неактивний обліковий запис: {account['name']}")
                continue
            
            relevant_channels = [ch for ch in self.config["channels"]
                            if ch["enabled"] and account["phone"] in ch.get("accounts", [])]
            if not relevant_channels:
                log_callback(f"⏭️ Обліковий запис {account['name']} не призначено до жодного каналу")
                continue
            
            accounts_to_auth.append((account, relevant_channels))
        
        for account, relevant_channels in accounts_to_auth:
            log_callback(f"🔐 Авторизація облікового запису: {account['name']}")
            log_callback(f"📺 Канали для цього облікового запису: {[ch['username'] for ch in relevant_channels]}")
            
            client = await self.create_client(account, input_callback, log_callback)
            if client:
                self.clients[account["phone"]] = client
                log_callback(f"✅ Клієнт {account['phone']} додано до активних клієнтів")
                
                if account["phone"] not in self.channel_entities:
                    self.channel_entities[account["phone"]] = {}
                
                for channel_config in relevant_channels:
                    try:
                        entity = await client.get_entity(channel_config["username"])
                        self.channel_entities[account["phone"]][channel_config["username"]] = entity
                        log_callback(f"✅ Підключено до @{channel_config['username']}: {entity.title}")
                    except Exception as e:
                        log_callback(f"⚠️ Не вдалося підключитися до @{channel_config['username']}: {e}")
                
                await asyncio.sleep(2)
            else:
                log_callback(f"❌ Не вдалося авторизувати {account['name']}")
        
        if not self.clients:
            log_callback("❌ Жодного клієнта не створено!")
        else:
            log_callback(f"✅ Авторизовано {len(self.clients)} клієнт(ів)")
    
    async def send_reaction(self, client: TelegramClient, chat_entity, message_id: int) -> bool:
        try:
            reactions = ["👍", "❤️", "🔥", "👏", "😍", "💯"]
            reaction = random.choice(reactions)
            
            await client(SendReactionRequest(
                peer=chat_entity,
                msg_id=message_id,
                reaction=[ReactionEmoji(emoticon=reaction)]
            ))
            return True
        except Exception as e:
            logger.debug(f"Не вдалося надіслати реакцію: {e}")
            return False
    
    async def get_discussion_message(self, client: TelegramClient, channel_entity, message_id: int):
        try:
            result = await client(GetDiscussionMessageRequest(
                peer=channel_entity,
                msg_id=message_id
            ))
            return result
        except Exception as e:
            logger.debug(f"Не вдалося отримати повідомлення дискусії: {e}")
            return None
    
    async def like_random_reply(self, client: TelegramClient, discussion_chat, discussion_message_id: int, account_phone: str):
        try:
            if random.random() > self.config["comment_settings"]["reply_like_probability"]:
                return
            
            messages = await client.get_messages(discussion_chat, limit=10, min_id=discussion_message_id)
            other_replies = [msg for msg in messages if msg.id > discussion_message_id and not msg.out]
            
            if other_replies:
                random_reply = random.choice(other_replies)
                await self.send_reaction(client, discussion_chat, random_reply.id)
                self.log_activity(account_phone, "discussion", "REPLY_LIKE", random_reply.id)
        except Exception as e:
            logger.debug(f"Не вдалося поставити лайк на відповідь: {e}")
    
    async def simulate_typing(self, client: TelegramClient, chat, text: str):
        char_delay = random.uniform(0.02, 0.05)
        for _ in range(len(text)):
            await asyncio.sleep(char_delay + random.uniform(0, 0.01))
    
    async def send_comment_to_discussion(self, client: TelegramClient, channel_entity, message_id: int, 
                                    comment_text: str, account_phone: str, log_callback=None) -> bool:
        try:
            discussion = await self.get_discussion_message(client, channel_entity, message_id)
            
            if not discussion or not hasattr(discussion, 'messages') or not discussion.messages:
                if log_callback:
                    log_callback(f"[{account_phone}] Немає групи дискусії для повідомлення {message_id}")
                return False
            
            discussion_chat = discussion.chats[0] if discussion.chats else None
            if not discussion_chat:
                if log_callback:
                    log_callback(f"[{account_phone}] Групу дискусії не знайдено")
                return False
            
            discussion_message = discussion.messages[0]
            discussion_message_id = discussion_message.id
            
            await self.simulate_typing(client, discussion_chat, comment_text)
            
            await client.send_message(
                discussion_chat,
                comment_text,
                reply_to=discussion_message_id
            )
            
            await self.like_random_reply(client, discussion_chat, discussion_message_id, account_phone)
            
            if log_callback:
                log_callback(f"[{account_phone}] Коментар надіслано: {comment_text[:50]}...")
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"[{account_phone}] Не вдалося надіслати коментар: {e}")
            return False
    
    async def simulate_silent_activity(self, client: TelegramClient, channel_entity, account_phone: str):
        try:
            await client.get_messages(channel_entity, limit=1)
            self.log_activity(account_phone, channel_entity.username, "SILENT_VIEW")
        except Exception as e:
            logger.debug(f"Тиха активність не вдалася: {e}")
    
    async def process_new_message(self, client: TelegramClient, event, account_phone: str, log_callback=None):
            try:
                message = event.message
                if not message or isinstance(message, MessageService) or not message.text:
                    if log_callback:
                        log_callback(f"[{account_phone}] Пропуск невалідного повідомлення")
                    return

                chat = await event.get_chat()
                if not isinstance(chat, Channel) or not chat.username:
                    if log_callback:
                        log_callback(f"[{account_phone}] Пропуск неканалу або відсутність імені користувача")
                    return

                channel_username = chat.username
                channel_config = next(
                    (ch for ch in self.config["channels"] 
                    if ch["username"] == channel_username and ch["enabled"]),
                    None
                )
                if not channel_config:
                    if log_callback:
                        log_callback(f"[{account_phone}] Канал {channel_username} не налаштовано")
                    return

                available_accounts = [
                    phone for phone in self.clients.keys()
                    if any(acc["phone"] == phone and acc["active"] for acc in self.config["accounts"])
                ]
                selected_accounts = self.get_random_accounts_for_channel(channel_username, available_accounts)

                if account_phone not in selected_accounts:
                    self.mark_post_processed(message.id, channel_username, account_phone)
                    if log_callback:
                        log_callback(f"[{account_phone}] Не вибрано для коментування")
                    return

                if self.is_post_processed(message.id, channel_username, account_phone):
                    if log_callback:
                        log_callback(f"[{account_phone}] Повідомлення {message.id} уже оброблено")
                    return

                if log_callback:
                    log_callback(f"[{account_phone}] Обробка повідомлення {message.id} у @{channel_username}")

                if random.random() < self.config["comment_settings"]["silent_activity_probability"]:
                    await self.simulate_silent_activity(client, chat, account_phone)
                    self.mark_post_processed(message.id, channel_username, account_phone)
                    return

                min_delay_sec = self.config["comment_settings"]["min_delay"] * 60
                max_delay_sec = self.config["comment_settings"]["max_delay"] * 60
                delay = random.randint(min_delay_sec, max_delay_sec)

                if log_callback:
                    log_callback(f"[{account_phone}] Заплановано для @{channel_username} через {delay//60} хв {delay%60} сек")

                await asyncio.sleep(delay)

                if random.random() < self.config["comment_settings"]["like_probability"]:
                    if await self.send_reaction(client, chat, message.id):
                        self.log_activity(account_phone, channel_username, "REACTION", message.id)
                
                if random.random() < self.config["comment_settings"]["comment_probability"]:
                    sticker_settings = self.config.get("sticker_settings", {})
                    if sticker_settings.get("enabled", False) and random.random() < sticker_settings.get("probability", 0.15):
                        sticker_id = self.get_random_sticker()
                        if sticker_id:
                            await asyncio.sleep(random.uniform(1, 5))
                            try:
                                if await self.send_sticker_to_discussion(
                                    client, chat, message.id, sticker_id, account_phone, log_callback
                                ):
                                    self.log_activity(account_phone, channel_username, "STICKER", message.id, "sticker")
                                    if log_callback:
                                        log_callback(f"[{account_phone}] Стикер надіслано!")
                            except FloodWaitError as e:
                                if log_callback:
                                    log_callback(f"[{account_phone}] FloodWait: {e.seconds} секунд")
                                await asyncio.sleep(e.seconds)
                            except Exception as e:
                                if log_callback:
                                    log_callback(f"[{account_phone}] Помилка стикера: {e}")
                    else:
                        style = self.get_weighted_style()
                        lang = self.detect_language(message.text)
                        comment_text = await self.generate_comment(message.text, style, lang)

                        if comment_text:
                            await asyncio.sleep(random.uniform(1, 5))
                            try:
                                if await self.send_comment_to_discussion(
                                    client, chat, message.id, comment_text, account_phone, log_callback
                                ):
                                    self.log_activity(account_phone, channel_username, "COMMENT", message.id, comment_text)
                                    if log_callback:
                                        log_callback(f"[{account_phone}] Коментар надіслано: {comment_text[:50]}...")
                            except FloodWaitError as e:
                                if log_callback:
                                    log_callback(f"[{account_phone}] FloodWait: {e.seconds} секунд")
                                await asyncio.sleep(e.seconds)
                            except Exception as e:
                                if log_callback:
                                    log_callback(f"[{account_phone}] Помилка коментаря: {e}")

                self.mark_post_processed(message.id, channel_username, account_phone)
                
            except Exception as e:
                if log_callback:
                    log_callback(f"[{account_phone}] Помилка обробки повідомлення: {e}")
                logger.error(f"Помилка в process_new_message для {account_phone}: {e}")

    def toggle_stickers(self, enabled: bool = None, probability: float = None) -> dict:
        if "sticker_settings" not in self.config:
            self.config["sticker_settings"] = {
                "enabled": False,
                "probability": 0.15,
                "use_standard_stickers": True,
                "custom_stickers": []
            }
        
        if enabled is not None:
            self.config["sticker_settings"]["enabled"] = enabled
        
        if probability is not None:
            self.config["sticker_settings"]["probability"] = min(1.0, max(0.0, probability))
        
        self.save_config()
        return self.config["sticker_settings"]

    def add_custom_sticker(self, sticker_file_id: str) -> bool:
        if "sticker_settings" not in self.config:
            self.config["sticker_settings"] = {
                "enabled": False,
                "probability": 0.15,
                "use_standard_stickers": True,
                "custom_stickers": []
            }
        
        if sticker_file_id not in self.config["sticker_settings"]["custom_stickers"]:
            self.config["sticker_settings"]["custom_stickers"].append(sticker_file_id)
            self.save_config()
            return True
        return False
    
    async def setup_event_handlers(self, log_callback):
        for phone, client in self.clients.items():
            relevant_channels = [ch["username"] for ch in self.config["channels"] 
                            if ch["enabled"] and phone in ch.get("accounts", [])]
            
            log_callback(f"📋 Аккаунт {phone} буде слухати: {relevant_channels}")
            
            for channel_username in relevant_channels:
                try:
                    entity = await client.get_entity(channel_username)
                    log_callback(f"✅ Канал @{channel_username} знайдено: {entity.title}")
                    messages = await client.get_messages(entity, limit=1)
                    if messages:
                        log_callback(f"🔍 Останнє повідомлення ID: {messages[0].id}")
                    else:
                        log_callback(f"⚠️ Немає повідомлень в @{channel_username}")
                except Exception as e:
                    log_callback(f"❌ Помилка доступу до @{channel_username}: {e}")
                    return
            
            def make_handler(account_phone, client_instance):
                async def handler(event):
                    log_callback(f"🔍 Отримано подію від {account_phone} в каналі {event.chat.username if event.chat else 'Unknown'}")
                    log_callback(f"🔍 Повідомлення: {event.message.text[:50] if event.message and event.message.text else 'Немає тексту'}...")
                    task = asyncio.create_task(
                        self.process_new_message(client_instance, event, account_phone, log_callback)
                    )
                    self.active_tasks.append(task)
                return handler
            
            try:
                client.add_event_handler(
                    make_handler(phone, client),
                    events.NewMessage(chats=relevant_channels)
                )
                log_callback(f"✅ Обробник подій додано для {phone} на канали: {relevant_channels}")
            except Exception as e:
                log_callback(f"❌ Помилка додавання обробника для {phone}: {e}")
    
    async def start_monitoring_gui(self, log_callback):
        if self.monitoring_active and self.clients:
            log_callback("⚠️ Зупиняємо попередній моніторинг...")
            self.monitoring_active = False
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
            for client in list(self.clients.values()):
                try:
                    await client.disconnect()
                    log_callback(f"🔌 Клієнт {client.session.filename} відключено")
                except Exception as e:
                    log_callback(f"Помилка відключення клієнта: {e}")
            self.clients.clear()
            self.active_tasks.clear()
            await asyncio.sleep(1)

        if not self.clients:
            log_callback("❌ Жодного активного клієнта немає. Ініціалізація клієнтів...")
            await self.initialize_clients_gui(None, log_callback)

        if not self.clients:
            log_callback("❌ Не вдалося ініціалізувати жодного клієнта")
            return

        self.monitoring_active = True
        log_callback(f"🚀 Запуск моніторингу з {len(self.clients)} обліковими записами")
        
        await self.setup_event_handlers(log_callback)
        
        async def cleanup_tasks():
            while self.monitoring_active:
                active_count = len([task for task in self.active_tasks if not task.done()])
                if active_count > 0:
                    log_callback(f"🔍 Активних завдань: {active_count}")
                self.active_tasks = [task for task in self.active_tasks if not task.done()]
                await asyncio.sleep(60)
        
        cleanup_task = asyncio.create_task(cleanup_tasks())
        
        log_callback("✅ Моніторинг розпочато - очікування повідомлень...")
        log_callback("🔍 Перевірте, що в каналі увімкнено коментарі!")
        
        try:
            while self.monitoring_active:
                for phone, client in list(self.clients.items()):
                    try:
                        if not await client.is_user_authorized():
                            log_callback(f"❌ Клієнт {phone} втратив авторизацію")
                            await client.disconnect()
                            del self.clients[phone]
                    except Exception as e:
                        log_callback(f"❌ Помилка перевірки клієнта {phone}: {e}")
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            log_callback("🛑 Зупинка моніторингу...")
        finally:
            self.monitoring_active = False
            cleanup_task.cancel()
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
            for client in list(self.clients.values()):
                try:
                    await client.disconnect()
                    log_callback(f"🔌 Клієнт {client.session.filename} відключено")
                except Exception as e:
                    log_callback(f"Помилка відключення клієнта: {e}")
            self.clients.clear()
            log_callback("✅ Моніторинг завершено, всі клієнти відключено")
    
    def show_statistics_text(self) -> str:
        conn = sqlite3.connect(self.db_path, timeout=30)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT account, channel, action, COUNT(*) 
            FROM activity_log 
            WHERE timestamp > datetime('now', '-24 hours')
            GROUP BY account, channel, action
        ''')
        
        stats = cursor.fetchall()
        stat_text = "📊 Статистика за останні 24 години:\n"
        stat_text += "-" * 50 + "\n"
        
        if stats:
            for account, channel, action, count in stats:
                stat_text += f"{account} у @{channel}: {action} - {count}\n"
        else:
            stat_text += "Жодної активності за останні 24 години\n"
        
        cursor.execute('''
            SELECT COUNT(*) FROM activity_log 
            WHERE timestamp > datetime('now', '-24 hours')
        ''')
        total = cursor.fetchone()[0]
        stat_text += f"\nЗагальна кількість дій: {total}"
        
        conn.close()
        return stat_text
    
    def show_accounts_status_text(self) -> str:
        status_text = "👥 Статус облікових записів:\n"
        status_text += "-" * 50 + "\n"
        for account in self.config["accounts"]:
            status = "🟢 Активний" if account["active"] else "🔴 Неактивний"
            connected = "🔗 Підключено" if account["phone"] in self.clients else "⌐ Відключено"
            channels = [ch["username"] for ch in self.config["channels"] if account["phone"] in ch.get("accounts", [])]
            channels_str = f"Канали: {', '.join(channels)}" if channels else "Канали: немає"
            status_text += f"{account['name']} ({account['phone']}): {status} | {connected} | {channels_str}\n"
        return status_text
    
    def show_channels_status_text(self) -> str:
        status_text = "📺 Статус каналів:\n"
        status_text += "-" * 50 + "\n"
        if not self.config["channels"]:
            status_text += "Жодного каналу не додано\n"
            return status_text
                
        for i, channel in enumerate(self.config["channels"], 1):
            status = "🟢 Активний" if channel["enabled"] else "🔴 Вимкнено"
            accounts = [acc["name"] for acc in self.config["accounts"] if acc["phone"] in channel.get("accounts", [])]
            accounts_str = f"Облікові записи: {', '.join(accounts)}" if accounts else "Облікові записи: немає"
            status_text += f"{i}. @{channel['username']}: {status} | {accounts_str}\n"
            status_text += f"   Посилання: https://t.me/{channel['username']}\n\n"
        return status_text