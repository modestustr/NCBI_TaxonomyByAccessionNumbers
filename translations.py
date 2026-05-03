"""
Translation/Localization system for TaxoByAccession Streamlit application
Supports multiple languages: Turkish (tr), English (en)
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path

class Translator:
    """
    Manages translations for the application.
    Loads translation files and provides translation methods.
    """
    
    # Default language
    DEFAULT_LANGUAGE = "tr"
    
    # Supported languages
    SUPPORTED_LANGUAGES = {
        "tr": "Türkçe",
        "en": "English"
    }
    
    def __init__(self, translations_dir: str = None):
        """
        Initialize the translator.
        
        Args:
            translations_dir: Directory containing translation JSON files.
                             If None, uses the current script directory.
        """
        if translations_dir is None:
            translations_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.translations_dir = translations_dir
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.current_language = self.DEFAULT_LANGUAGE
        
        # Load all available translations
        self._load_translations()
    
    def _load_translations(self) -> None:
        """Load all translation files from the translations directory."""
        for lang_code in self.SUPPORTED_LANGUAGES.keys():
            translation_file = os.path.join(
                self.translations_dir, 
                f"translations_{lang_code}.json"
            )
            
            if os.path.exists(translation_file):
                try:
                    with open(translation_file, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Warning: Could not load translation file {translation_file}: {e}")
                    self.translations[lang_code] = {}
    
    def set_language(self, language: str) -> bool:
        """
        Set the current language.
        
        Args:
            language: Language code (e.g., 'tr', 'en')
            
        Returns:
            True if language was set successfully, False otherwise
        """
        if language in self.SUPPORTED_LANGUAGES:
            self.current_language = language
            return True
        return False
    
    def get_language(self) -> str:
        """Get the current language code."""
        return self.current_language
    
    def get_language_name(self, language_code: str = None) -> str:
        """
        Get the native name of a language.
        
        Args:
            language_code: Language code. If None, uses current language.
            
        Returns:
            Language name (e.g., 'Türkçe', 'English')
        """
        if language_code is None:
            language_code = self.current_language
        
        return self.SUPPORTED_LANGUAGES.get(language_code, language_code)
    
    def translate(self, key: str, *args, **kwargs) -> str:
        """
        Translate a key to the current language.
        
        Supports nested keys using dot notation: 'section.subsection.key'
        Supports simple string formatting with positional and keyword arguments.
        
        Args:
            key: Translation key (supports dot notation for nested keys)
            *args: Positional arguments for string formatting
            **kwargs: Keyword arguments for string formatting
            
        Returns:
            Translated string, or the key itself if translation not found
        """
        # Get translation from current language
        translation = self._get_nested_key(
            self.translations.get(self.current_language, {}),
            key
        )
        
        # Fallback to default language if not found
        if translation is None:
            translation = self._get_nested_key(
                self.translations.get(self.DEFAULT_LANGUAGE, {}),
                key
            )
        
        # Fallback to key itself if still not found
        if translation is None:
            return key
        
        # Apply string formatting if arguments provided
        try:
            if args or kwargs:
                return translation.format(*args, **kwargs)
            return translation
        except (IndexError, KeyError):
            # If formatting fails, return unformatted translation
            return translation
    
    def t(self, key: str, *args, **kwargs) -> str:
        """
        Shorthand for translate() method.
        
        Args:
            key: Translation key
            *args: Positional arguments for formatting
            **kwargs: Keyword arguments for formatting
            
        Returns:
            Translated string
        """
        return self.translate(key, *args, **kwargs)
    
    @staticmethod
    def _get_nested_key(dictionary: Dict, key: str) -> Optional[Any]:
        """
        Get a value from a nested dictionary using dot notation.
        
        Args:
            dictionary: The dictionary to search
            key: The key path (e.g., 'section.subsection.key')
            
        Returns:
            The value if found, None otherwise
        """
        keys = key.split('.')
        current = dictionary
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        
        return current if isinstance(current, str) else None
    
    def get_all_languages(self) -> Dict[str, str]:
        """
        Get all supported languages.
        
        Returns:
            Dictionary of language codes to language names
        """
        return self.SUPPORTED_LANGUAGES.copy()


# Global translator instance
_translator: Optional[Translator] = None


def initialize_translator(translations_dir: str = None) -> Translator:
    """
    Initialize the global translator instance.
    
    Args:
        translations_dir: Directory containing translation files
        
    Returns:
        The initialized Translator instance
    """
    global _translator
    _translator = Translator(translations_dir)
    return _translator


def get_translator() -> Translator:
    """
    Get the global translator instance.
    Initialize it if not already done.
    
    Returns:
        The global Translator instance
    """
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def set_language(language: str) -> bool:
    """
    Convenience function to set the global translator's language.
    
    Args:
        language: Language code
        
    Returns:
        True if successful
    """
    return get_translator().set_language(language)


def t(key: str, *args, **kwargs) -> str:
    """
    Convenience function for translating text using the global translator.
    
    Args:
        key: Translation key
        *args: Positional formatting arguments
        **kwargs: Keyword formatting arguments
        
    Returns:
        Translated string
    """
    return get_translator().translate(key, *args, **kwargs)
