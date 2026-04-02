import sys

from PyQt5.QtWidgets import QApplication

from chemunited.qt.setup import SetupWindow


def main():
    app = QApplication(sys.argv)
    window = SetupWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
