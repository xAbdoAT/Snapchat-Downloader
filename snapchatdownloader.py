import sys
from PyQt5.QtWidgets import (QApplication, QWidget, QLineEdit, QPushButton,
                             QVBoxLayout, QHBoxLayout, QProgressBar, QTextEdit,
                             QListWidget, QMessageBox)
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QIcon
import os
import requests
from bs4 import BeautifulSoup
import json
from time import sleep

class DownloadThread(QThread):
    update_progress = pyqtSignal(int)
    update_log = pyqtSignal(str)
    download_complete = pyqtSignal()

    def __init__(self, userslist):
        super().__init__()
        self.userslist = userslist
        self.is_cancelled = False

    def run(self):

        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.join(script_dir, "Downloads")

        for idx, username in enumerate(self.userslist):
            if self.is_cancelled:
                break

            user_path = os.path.join(base_path, username)
            os.makedirs(user_path, exist_ok=True)

            from datetime import datetime
            date_folder = datetime.now().strftime("%Y-%m-%d")
            download_path = os.path.join(user_path, date_folder)
            os.makedirs(download_path, exist_ok=True)

            os.chdir(download_path)

            json_dict = self.get_json(username)
            if json_dict:
                self.download_media(json_dict)
            self.update_progress.emit((idx + 1) * 100 // len(self.userslist))

        self.download_complete.emit()

    def get_json(self, username):
        base_url = "https://story.snapchat.com/@"
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/103.0.2'}
        mix = base_url + username
        r = requests.get(mix, headers=headers)

        if not r.ok:
            self.update_log.emit("Oh Snap! No connection with Snap!")
            return None

        soup = BeautifulSoup(r.content, "html.parser")
        snaps = soup.find(id="__NEXT_DATA__").string.strip()
        data = json.loads(snaps)

        return data

    def download_media(self, json_dict):
        try:
            for i in json_dict["props"]["pageProps"]["story"]["snapList"]:
                if self.is_cancelled:
                    return

                retries = 3
                while retries > 0 and not self.is_cancelled:
                    try:
                        file_url = i["snapUrls"]["mediaUrl"]
                        if not file_url:
                            self.update_log.emit("There is a Story but no URL is provided by Snapchat.")
                            break

                        r = requests.get(file_url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)

                        if "image" in r.headers['Content-Type']:
                            file_name = r.headers['ETag'].replace('"', '') + ".jpeg"
                        elif "video" in r.headers['Content-Type']:
                            file_name = r.headers['ETag'].replace('"', '') + ".mp4"
                        else:
                            continue

                        current_dir = os.getcwd()
                        full_path = os.path.join(current_dir, file_name)

                        if os.path.isfile(full_path):
                            self.update_log.emit(f"File already exists: {file_name}")
                            break

                        sleep(0.3)

                        if r.status_code == 200:
                            with open(full_path, 'wb') as f:
                                for chunk in r:
                                    f.write(chunk)
                            self.update_log.emit(f"Downloaded {file_name}")
                            break  
                        else:
                            self.update_log.emit("[-] Cannot make connection to download media!")
                            break
                    except requests.RequestException as e:
                        if self.is_cancelled:
                            return
                        retries -= 1
                        if retries == 0:
                            self.update_log.emit(f"Failed to download after 3 attempts: {str(e)}")
                        else:
                            sleep(1)
                            continue
        except KeyError:
            self.update_log.emit("[-] No stories found for the last 24h.\n")

class SnapchatDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.userslist = []
        self.download_queue = []
        self.is_downloading = False
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Snapchat Downloader')
        self.setWindowIcon(QIcon('snap.png'))

        main_layout = QVBoxLayout()
        form_layout = QVBoxLayout()
        user_list_layout = QVBoxLayout()

        self.setStyleSheet("""
            QWidget {
                font-size: 14px;
            }
            QLineEdit, QTextEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #5cb85c;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4cae4c;
            }
            QProgressBar {
                height: 20px;
                text-align: center;
            }
            QListWidget {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: black;
                color: white;
                font-family: Consolas, monospace;
            }
        """)

        self.user_list_widget = QListWidget()
        self.new_user_input = QLineEdit()
        self.new_user_input.setPlaceholderText('Enter Snapchat username')
        self.add_user_button = QPushButton('Add User')
        self.remove_user_button = QPushButton('Remove Selected')

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.new_user_input)
        input_layout.addWidget(self.add_user_button)
        input_layout.addWidget(self.remove_user_button)

        list_management_layout = QHBoxLayout()
        self.save_list_button = QPushButton('Save List')
        self.load_list_button = QPushButton('Load List')
        list_management_layout.addWidget(self.save_list_button)
        list_management_layout.addWidget(self.load_list_button)

        self.progress_bar = QProgressBar()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.download_button = QPushButton('Download')

        self.add_user_button.clicked.connect(self.add_user)
        self.remove_user_button.clicked.connect(self.remove_user)
        self.save_list_button.clicked.connect(self.save_userlist)
        self.load_list_button.clicked.connect(self.load_userlist)
        self.download_button.clicked.connect(self.start_download)

        user_list_layout.addWidget(self.user_list_widget)
        user_list_layout.addLayout(input_layout)
        user_list_layout.addLayout(list_management_layout)

        form_layout.addLayout(user_list_layout)
        form_layout.addWidget(self.progress_bar)
        form_layout.addWidget(self.log_area)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.download_button)

        self.setLayout(main_layout)
        self.resize(500, 600)

    def add_user(self):
        new_user = self.new_user_input.text().strip()
        if new_user and new_user not in self.userslist:
            self.userslist.append(new_user)
            self.user_list_widget.addItem(new_user)
            self.new_user_input.clear()
        else:
            QMessageBox.warning(self, "Error", "Invalid or duplicate username.")

    def remove_user(self):
        selected_items = self.user_list_widget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.userslist.remove(item.text())
            self.user_list_widget.takeItem(self.user_list_widget.row(item))

    def start_download(self):
        if not self.userslist:
            QMessageBox.warning(self, "Error", "Please add at least one user before downloading.")
            return

        if self.is_downloading:
            self.thread.is_cancelled = True
            self.download_button.setDisabled(True)
            self.download_button.setText('Cancelling...')
            return

        self.is_downloading = True
        self.download_button.setText('Cancel Download')
        self.download_button.setEnabled(True)  
        self.log_area.clear()
        self.progress_bar.setValue(0)
        self.thread = DownloadThread(self.userslist)
        self.thread.update_progress.connect(self.update_progress)
        self.thread.update_log.connect(self.update_log)
        self.thread.download_complete.connect(self.download_complete)
        self.thread.start()

    def download_complete(self):
        self.is_downloading = False
        self.download_button.setText('Download')
        self.download_button.setEnabled(True)
        self.progress_bar.setValue(0)
        if not self.thread.is_cancelled:
            QMessageBox.information(self, "Download Complete", "Downloaded successfully.")
        else:
            self.log_area.append("Download cancelled by user.")

    def save_userlist(self):
        if not self.userslist:
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        userlist_path = os.path.join(script_dir, 'userlist.txt')
        with open(userlist_path, 'w') as f:
            f.write('\n'.join(self.userslist))

    def load_userlist(self):
        try:

            script_dir = os.path.dirname(os.path.abspath(__file__))
            userlist_path = os.path.join(script_dir, 'userlist.txt')
            with open(userlist_path, 'r') as f:
                users = f.read().splitlines()
                for user in users:
                    if user.strip() and user not in self.userslist:
                        self.userslist.append(user)
                        self.user_list_widget.addItem(user)
        except FileNotFoundError:
            pass

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        self.log_area.append(message)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SnapchatDownloader()
    ex.show()
    sys.exit(app.exec_())
