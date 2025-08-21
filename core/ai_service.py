"""
Модуль для работы с OpenAI API (GPT-4 и Whisper)
"""
import os
import io
import tempfile
from openai import AsyncOpenAI
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from core.config import AI_SETTINGS, DEFAULT_SYSTEM_PROMPT, WHISPER_SETTINGS


class AIService:
    """Сервис для работы с OpenAI API"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def build_prompt(self, profile_info: str = "") -> str:
        """Построение персонализированного промпта"""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = DEFAULT_SYSTEM_PROMPT
        prompt += f"\n\n# Current date\nToday is {today_str}."
        
        if profile_info:
            prompt += f"\n\n# User context\n{profile_info.strip()}"
        
        return prompt
    
    def format_profile_info(self, profile: Optional[Tuple]) -> str:
        """Форматирование информации профиля"""
        if not profile:
            return ""
        
        gender, age_group, lucid = profile
        profile_parts = []
        
        if gender:
            profile_parts.append(f"User gender: {gender}")
        if age_group:
            profile_parts.append(f"User age group: {age_group}")
        if lucid:
            profile_parts.append(f"Lucid dream experience: {lucid}")
        
        return ". ".join(profile_parts) + ("." if profile_parts else "")
    
    async def analyze_dream(self, dream_text: str, history: List[Dict], profile_info: str = "") -> str:
        """Анализ сна через GPT-4"""
        try:
            prompt = self.build_prompt(profile_info)
            
            response = await self.client.chat.completions.create(
                model=AI_SETTINGS["model"],
                messages=[{"role": "system", "content": prompt}] + history,
                temperature=AI_SETTINGS["temperature"],
                max_tokens=AI_SETTINGS["max_tokens"]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ Ошибка при анализе сна: {e}"
    
    def extract_message_type(self, ai_response: str) -> str:
        """Извлечение типа сообщения из ответа AI"""
        if ai_response.startswith('🌙'):
            return 'dream'
        elif ai_response.startswith('❓'):
            return 'question'
        elif ai_response.startswith('💭'):
            return 'chat'
        else:
            return 'unknown'
    
    async def transcribe_voice(self, voice_file_content: bytes, file_extension: str = "ogg") -> Optional[str]:
        """Транскрипция голосового сообщения через Whisper"""
        temp_file_path = None
        
        try:
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_file:
                temp_file.write(voice_file_content)
                temp_file_path = temp_file.name
            
            # Транскрибируем через Whisper
            with open(temp_file_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ru"
                )
                
                return transcript.text.strip()
                
        except Exception as e:
            print(f"❌ Ошибка транскрипции: {e}")
            return None
            
        finally:
            # Удаляем временный файл
            if temp_file_path:
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
    
    def is_transcription_suspicious(self, transcribed_text: str, voice_duration: float) -> Tuple[bool, str]:
        """Проверка транскрипции на подозрительность (галлюцинации Whisper)"""
        if not transcribed_text:
            return True, "empty_text"
        
        text_lower = transcribed_text.lower()
        words = text_lower.split()
        
        # 1. Проверка на подозрительные фразы
        suspicious_phrases = WHISPER_SETTINGS["suspicious_phrases"]
        for phrase in suspicious_phrases:
            if phrase.lower() in text_lower:
                return True, f"suspicious_phrase: {phrase}"
        
        # 2. Слишком мало слов для длинного аудио (меньше 1 слова в 2 секунды)
        if voice_duration > 4 and len(words) < voice_duration / 2:
            return True, f"too_short_text: {len(words)} words for {voice_duration}s"
        
        # 3. Только междометия
        interjections = {"ммм", "хмм", "эм", "ага", "угу", "ой", "ах", "ох", "эх", "ух"}
        if all(word in interjections for word in words) and len(words) > 0:
            return True, "only_interjections"
        
        # 4. Повторяющиеся символы (ммммм, ааааа и т.д.)
        for word in words:
            if len(word) > 3 and len(set(word)) == 1:
                return True, f"repetitive_chars: {word}"
        
        return False, ""
    
    def should_reject_voice_message(self, transcribed_text: str, voice_duration: float) -> Tuple[bool, str]:
        """Определение, следует ли отклонить голосовое сообщение"""
        
        # Фильтруем очень короткие сообщения (вероятно случайные)
        if voice_duration < WHISPER_SETTINGS["min_duration"]:
            return True, f"too_short_duration: {voice_duration}s"
        
        # Проверяем на подозрительность
        is_suspicious, reason = self.is_transcription_suspicious(transcribed_text, voice_duration)
        
        if is_suspicious:
            # Для коротких аудио и фразовых совпадений отклоняем сразу
            if voice_duration < WHISPER_SETTINGS["max_duration_for_phrase_filter"] or "suspicious_phrase" in reason:
                return True, reason
            # Для длинных аудио можем быть менее строгими с некоторыми типами ошибок
            elif "too_short_text" not in reason:
                return True, reason
        
        return False, ""


# Глобальный экземпляр AI сервиса
ai_service = AIService()
