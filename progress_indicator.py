import time
import sys
from typing import Optional, Callable
from datetime import datetime
from pathlib import Path

class ProgressIndicator:
    def __init__(self, total: int, description: str = "Executing..."):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = datetime.now()
        self.last_update = self.start_time

    def update(self, current: int = None, increment: int = 1):
        if current is not None:
            self.current = current
        else:
            self.current += increment

        self.last_update = datetime.now()

    def finish(self):
        self.current = self.total
        self._display()
        print()

    def _display(self):
        pass

    def get_elapsed_time(self) -> str:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        elif elapsed < 3600:
            return f"{elapsed / 60:.1f}m"
        else:
            return f"{elapsed / 3600:.1f}h"

    def get_eta(self) -> str:
        if self.current == 0:
            return "N/A"

        elapsed = (datetime.now() - self.start_time).total_seconds()
        speed = self.current / elapsed if elapsed > 0 else 0
        remaining = (self.total - self.current) / speed if speed > 0 else 0

        if remaining < 60:
            return f"{remaining:.0f}s"
        elif remaining < 3600:
            return f"{remaining / 60:.1f}m"
        else:
            return f"{remaining / 3600:.1f}h"

class SimpleProgressBar(ProgressIndicator):
    def __init__(self, total: int, description: str = "Executing", width: int = 50, show_percentage: bool = True):
        super().__init__(total, description)
        self.width = width
        self.show_percentage = show_percentage
        self.last_display = ""

    def update(self, current: int = None, increment: int = 1):
        super().update(current, increment)
        self._display()

    def _display(self):
        progress = self.current / self.total if self.total > 0 else 0
        filled = int(self.width * progress)
        bar = "█" * filled + "░" * (self.width - filled)

        if self.show_percentage:
            percentage = progress * 100
            percentage_str = f"{percentage:5.1f}%"
        else:
            progress_str = f"{self.current}/{self.total}"

        eta = self.get_eta()

        sys.stdout.write('\r' + ' ' * len(self._last_display))
        sys.stdout.write('\r')

        # Формируем вывод
        display = f"{self.description} |{bar}| {progress_str} [{self.current}/{self.total}] ETA: {eta}"

        # Сохраняем для очистки
        self._last_display = display

        sys.stdout.write(display)
        sys.stdout.flush()


class SpinnerIndicator(ProgressIndicator):
    def __init__(self, description: str = "Executing", spinner_chars: list = None):
        super().__init__(0, description)
        self.spinner_chars = spinner_chars or ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self._current_spinner = 0

    def update(self, current: int = None, increment: int = 1):
        super().update(current, increment)
        self._display()

    def _display(self):
        """Отображает спиннер"""
        char = self.spinner_chars[self._current_spinner % len(self.spinner_chars)]
        self._current_spinner += 1

        elapsed = self.get_elapsed_time()
        progress_str = f"{self.current} files" if self.current > 0 else "prepairing..."

        display = f"{char} {self.description} - {progress_str} (time: {elapsed})"

        sys.stdout.write('\r' + ' ' * len(self._last_display) if hasattr(self, '_last_display') else '')
        sys.stdout.write('\r')
        sys.stdout.write(display)
        sys.stdout.flush()

        self._last_display = display


class ProgressWithLogging(ProgressIndicator):
    def __init__(self, total: int, description: str = "Executing",
                 logger=None, log_interval: int = 10):
        super().__init__(total, description)
        self.logger = logger
        self.log_interval = log_interval
        self._last_logged = 0

    def update(self, current: int = None, increment: int = 1):
        super().update(current, increment)

        # Логируем каждые log_interval шагов
        if self.logger and (self.current - self._last_logged) >= self.log_interval:
            self._last_logged = self.current
            progress = (self.current / self.total * 100) if self.total > 0 else 0
            self.logger.info(f"Progress: {self.current}/{self.total} ({progress:.1f}%)")


class MultiProgressManager:
    def __init__(self):
        self.indicators = []
        self.current_indicator = None

    def add_indicator(self, indicator: ProgressIndicator):
        self.indicators.append(indicator)

    def start_indicator(self, index: int = 0):
        if index < len(self.indicators):
            self.current_indicator = self.indicators[index]
            self.current_indicator.update(0)

    def finish_all(self):
        for indicator in self.indicators:
            indicator.finish()


def get_progress_indicator(total: int, description: str = "Executing",
                           use_tqdm: bool = True) -> ProgressIndicator:
    try:
        if use_tqdm:
            from tqdm import tqdm
            return TqdmWrapper(total, description)
    except ImportError:
        pass
    return SimpleProgressBar(total, description)


class TqdmWrapper(ProgressIndicator):
    def __init__(self, total: int, description: str = "Executing"):
        super().__init__(total, description)
        try:
            from tqdm import tqdm
            self.tqdm = tqdm(
                total=total,
                desc=description,
                unit="файлов",
                ncols=80,
                bar_format="{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
            )
        except ImportError:
            self.tqdm = None

    def update(self, current: int = None, increment: int = 1):
        super().update(current, increment)
        if self.tqdm:
            if current is not None:
                self.tqdm.n = current
            else:
                self.tqdm.update(increment)
            self.tqdm.refresh()

    def finish(self):
        if self.tqdm:
            self.tqdm.close()

    def _display(self):
        # tqdm сам управляет отображением
        pass


class ProgressContext:
    def __init__(self, total: int, description: str = "Executing",
                 logger=None, use_tqdm: bool = True):
        self.total = total
        self.description = description
        self.logger = logger
        self.use_tqdm = use_tqdm
        self.indicator = None

    def __enter__(self):
        self.indicator = get_progress_indicator(
            self.total, self.description, self.use_tqdm
        )
        return self.indicator

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.indicator:
            self.indicator.finish()

        # Логируем завершение
        if self.logger and not exc_type:
            self.logger.info(f"Completed: {self.description} - {self.total} files")