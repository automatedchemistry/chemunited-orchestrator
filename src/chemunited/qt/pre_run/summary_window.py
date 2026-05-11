from PyQt5.QtWidgets import QMainWindow
from pathlib import Path


class SummaryWindow(QMainWindow):

    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent=parent)
        self._file_path = file_path

    @classmethod
    def inspect_file(cls, file_path: Path) -> "SummaryWindow":
        return cls(file_path)
        
        

            
        
