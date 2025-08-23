"""
Модуль для работы с базой данных PostgreSQL
"""
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from core.config import DATABASE_CONFIG


class DatabaseManager:
    """Менеджер для работы с базой данных"""
    
    def __init__(self):
        self.conn = None
        self._connect()
        self._init_tables()
    
    def _connect(self):
        """Подключение к базе данных"""
        try:
            self.conn = psycopg2.connect(**DATABASE_CONFIG)
            self.conn.autocommit = True
            print("✅ Подключение к базе данных установлено")
        except Exception as e:
            print(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    def _init_tables(self):
        """Инициализация таблиц"""
        self.init_user_stats_table()
        self.init_messages_table()
        self.init_user_profile_table()
        self.init_user_activity_log_table()
        self.init_dreams_table()
        self.init_pending_dreams_table()
        self._migrate_database()
    
    def init_user_stats_table(self):
        """Создание таблицы статистики пользователей"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    chat_id VARCHAR(20) PRIMARY KEY,
                    username VARCHAR(100),
                    messages_sent INTEGER DEFAULT 0,
                    symbols_sent INTEGER DEFAULT 0,
                    starts_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
    
    def init_messages_table(self):
        """Создание таблицы сообщений"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    chat_id VARCHAR(20) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)
            # Индекс для быстрого поиска истории
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_chat_id_timestamp 
                ON messages (chat_id, timestamp DESC)
            """)
    
    def init_user_profile_table(self):
        """Создание таблицы профилей пользователей"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    chat_id VARCHAR(20) PRIMARY KEY,
                    username VARCHAR(100),
                    gender VARCHAR(20),
                    age_group VARCHAR(20),
                    lucid_dreaming VARCHAR(20),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
    
    def init_user_activity_log_table(self):
        """Создание таблицы логов активности"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_activity_log (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    username VARCHAR(100),
                    chat_id VARCHAR(20),
                    action VARCHAR(50),
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            """)
    
    def init_dreams_table(self):
        """Создание таблицы снов"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS dreams (
                    id SERIAL PRIMARY KEY,
                    chat_id VARCHAR(20) NOT NULL,
                    dream_text TEXT NOT NULL,
                    interpretation TEXT NOT NULL,
                    astrological_interpretation TEXT,
                    source_type VARCHAR(25) NOT NULL DEFAULT 'text',
                    created_at TIMESTAMP DEFAULT NOW(),
                    dream_date DATE DEFAULT CURRENT_DATE,
                    tags TEXT[] DEFAULT '{}'
                )
            """)
            # Индекс для быстрого поиска снов пользователя
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_dreams_chat_id_date 
                ON dreams (chat_id, created_at DESC)
            """)
    
    def init_pending_dreams_table(self):
        """Создание таблицы временных данных снов"""
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_dreams (
                    id SERIAL PRIMARY KEY,
                    chat_id VARCHAR(20) NOT NULL,
                    dream_text TEXT NOT NULL,
                    interpretation TEXT NOT NULL,
                    source_type VARCHAR(25) NOT NULL,
                    astrological_interpretation TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # Индекс для быстрого поиска временных данных
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_dreams_chat_id 
                ON pending_dreams (chat_id)
            """)
    
    # === ПОЛЬЗОВАТЕЛИ И СТАТИСТИКА ===
    
    def log_activity(self, user, chat_id: str, action: str, content: str = ""):
        """Логирование активности пользователя"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_activity_log (user_id, username, chat_id, action, content)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user.id,
                f"@{user.username}" if user.username else None,
                chat_id,
                action,
                content[:1000]
            ))
    
    def update_user_stats(self, user, chat_id: str, message_text: str):
        """Обновление статистики пользователя"""
        username = f"@{user.username}" if user.username else None
        
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_stats (chat_id, username, messages_sent, symbols_sent, updated_at)
                VALUES (%s, %s, 1, %s, now())
                ON CONFLICT (chat_id) DO UPDATE
                SET 
                    messages_sent = user_stats.messages_sent + 1,
                    symbols_sent = user_stats.symbols_sent + %s,
                    username = COALESCE(EXCLUDED.username, user_stats.username),
                    updated_at = now()
            """, (
                chat_id,
                username,
                len(message_text),
                len(message_text)
            ))
    
    def increment_start_count(self, user, chat_id: str):
        """Увеличение счетчика стартов"""
        username = f"@{user.username}" if user.username else None
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_stats (chat_id, username, starts_count, updated_at)
                VALUES (%s, %s, 1, now())
                ON CONFLICT (chat_id) DO UPDATE
                SET 
                    starts_count = user_stats.starts_count + 1,
                    username = COALESCE(EXCLUDED.username, user_stats.username),
                    updated_at = now()
            """, (
                chat_id,
                username
            ))
    
    def get_all_users(self) -> List[str]:
        """Получить список всех пользователей"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT chat_id
                FROM user_stats
                WHERE chat_id IS NOT NULL
                GROUP BY chat_id
                ORDER BY MAX(updated_at) DESC
            """)
            users = cur.fetchall()
            return [str(user[0]) for user in users]
    
    # === СООБЩЕНИЯ ===
    
    def save_message(self, chat_id: str, role: str, content: str):
        """Сохранение сообщения"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO messages (chat_id, role, content, timestamp)
                VALUES (%s, %s, %s, %s)
            """, (chat_id, role, content, datetime.now(timezone.utc)))
    
    def get_message_history(self, chat_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """Получение истории сообщений"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT role, content FROM messages
                WHERE chat_id = %s ORDER BY timestamp DESC LIMIT %s
            """, (chat_id, limit * 2))
            rows = cur.fetchall()
            return [{"role": r, "content": c} for r, c in reversed(rows)]
    
    # === ПРОФИЛИ ПОЛЬЗОВАТЕЛЕЙ ===
    
    def save_user_profile(self, chat_id: str, username: str, gender: str, age_group: str, lucid_dreaming: str):
        """Сохранение профиля пользователя"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_profile (chat_id, username, gender, age_group, lucid_dreaming, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (chat_id) DO UPDATE
                SET gender = EXCLUDED.gender,
                    age_group = EXCLUDED.age_group,
                    lucid_dreaming = EXCLUDED.lucid_dreaming,
                    updated_at = now()
            """, (chat_id, username, gender, age_group, lucid_dreaming))
    
    def get_user_profile(self, chat_id: str) -> Optional[Tuple]:
        """Получение профиля пользователя"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT gender, age_group, lucid_dreaming FROM user_profile
                WHERE chat_id = %s
            """, (chat_id,))
            return cur.fetchone()
    
    # === ДНЕВНИК СНОВ ===
    
    def save_dream(self, chat_id: str, dream_text: str, interpretation: str, 
                   source_type: str = 'text', dream_date: str = None, 
                   astrological_interpretation: str = None) -> bool:
        """Сохранение сна в дневник"""
        try:
            with self.conn.cursor() as cur:
                if dream_date:
                    cur.execute("""
                        INSERT INTO dreams (chat_id, dream_text, interpretation, astrological_interpretation, source_type, dream_date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (chat_id, dream_text, interpretation, astrological_interpretation, source_type, dream_date))
                else:
                    cur.execute("""
                        INSERT INTO dreams (chat_id, dream_text, interpretation, astrological_interpretation, source_type)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (chat_id, dream_text, interpretation, astrological_interpretation, source_type))
                return True
        except Exception as e:
            print(f"❌ Ошибка сохранения сна: {e}")
            return False
    
    def get_user_dreams(self, chat_id: str, limit: int = 10, offset: int = 0) -> List[Tuple]:
        """Получение снов пользователя с пагинацией"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, dream_text, interpretation, astrological_interpretation, source_type, created_at, dream_date
                FROM dreams
                WHERE chat_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (chat_id, limit, offset))
            return cur.fetchall()
    
    def count_user_dreams(self, chat_id: str) -> int:
        """Подсчет количества снов пользователя"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM dreams WHERE chat_id = %s
            """, (chat_id,))
            return cur.fetchone()[0]
    
    def get_dream_by_id(self, chat_id: str, dream_id: int) -> Optional[Tuple]:
        """Получение конкретного сна по ID"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT id, dream_text, interpretation, astrological_interpretation, source_type, created_at, dream_date
                FROM dreams
                WHERE chat_id = %s AND id = %s
            """, (chat_id, dream_id))
            return cur.fetchone()
    
    def delete_dream(self, chat_id: str, dream_id: int) -> bool:
        """Удаление сна"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM dreams
                    WHERE chat_id = %s AND id = %s
                """, (chat_id, dream_id))
                return cur.rowcount > 0
        except Exception as e:
            print(f"❌ Ошибка удаления сна: {e}")
            return False
    
    # === ВРЕМЕННЫЕ ДАННЫЕ СНОВ ===
    
    def save_pending_dream(self, chat_id: str, dream_text: str, interpretation: str, source_type: str) -> bool:
        """Сохранение временных данных сна для последующего сохранения в дневник"""
        try:
            with self.conn.cursor() as cur:
                # Сначала удаляем старые временные данные для этого пользователя
                cur.execute("""
                    DELETE FROM pending_dreams WHERE chat_id = %s
                """, (chat_id,))
                
                # Сохраняем новые временные данные
                cur.execute("""
                    INSERT INTO pending_dreams (chat_id, dream_text, interpretation, source_type, created_at)
                    VALUES (%s, %s, %s, %s, now())
                """, (chat_id, dream_text, interpretation, source_type))
                return True
        except Exception as e:
            print(f"❌ Ошибка сохранения временных данных сна: {e}")
            return False
    
    def get_pending_dream(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Получение временных данных сна"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT dream_text, interpretation, source_type, astrological_interpretation, created_at
                    FROM pending_dreams 
                    WHERE chat_id = %s
                    ORDER BY created_at DESC 
                    LIMIT 1
                """, (chat_id,))
                result = cur.fetchone()
                
                if result:
                    return {
                        'dream_text': result[0],
                        'interpretation': result[1],
                        'source_type': result[2],
                        'astrological_interpretation': result[3],
                        'created_at': result[4]
                    }
                return None
        except Exception as e:
            print(f"❌ Ошибка получения временных данных сна: {e}")
            return None
    
    def update_pending_dream_astrological(self, chat_id: str, astrological_interpretation: str) -> bool:
        """Обновление временных данных сна астрологическим толкованием"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    UPDATE pending_dreams 
                    SET astrological_interpretation = %s, updated_at = now()
                    WHERE chat_id = %s
                """, (astrological_interpretation, chat_id))
                return cur.rowcount > 0
        except Exception as e:
            print(f"❌ Ошибка обновления астрологического толкования: {e}")
            return False
    
    def delete_pending_dream(self, chat_id: str) -> bool:
        """Удаление временных данных сна"""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM pending_dreams WHERE chat_id = %s
                """, (chat_id,))
                return True
        except Exception as e:
            print(f"❌ Ошибка удаления временных данных сна: {e}")
            return False
    
    def _migrate_database(self):
        """Миграция базы данных"""
        try:
            with self.conn.cursor() as cur:
                # Проверяем текущий размер поля source_type
                cur.execute("""
                    SELECT column_name, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'dreams' AND column_name = 'source_type'
                """)
                result = cur.fetchone()
                
                if result and result[1] == 10:
                    # Увеличиваем размер поля с VARCHAR(10) до VARCHAR(25)
                    cur.execute("""
                        ALTER TABLE dreams 
                        ALTER COLUMN source_type TYPE VARCHAR(25)
                    """)
                    print("✅ Миграция БД: поле source_type увеличено до VARCHAR(25)")
                else:
                    print("✅ Миграция БД: поле source_type уже имеет нужный размер")
                
                # Проверяем наличие поля astrological_interpretation
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'dreams' AND column_name = 'astrological_interpretation'
                """)
                result = cur.fetchone()
                
                if not result:
                    # Добавляем поле astrological_interpretation
                    cur.execute("""
                        ALTER TABLE dreams 
                        ADD COLUMN astrological_interpretation TEXT
                    """)
                    print("✅ Миграция БД: добавлено поле astrological_interpretation")
                else:
                    print("✅ Миграция БД: поле astrological_interpretation уже существует")
                    
        except Exception as e:
            print(f"⚠️ Ошибка миграции БД: {e}")
            # Продолжаем работу, так как это не критично
    
    def close(self):
        """Закрытие соединения с БД"""
        if self.conn:
            self.conn.close()


# Глобальный экземпляр менеджера БД
db = DatabaseManager()
