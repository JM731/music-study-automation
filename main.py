import sys
from PyQt6.QtWidgets import (QApplication,
                             QMainWindow,
                             QPushButton,
                             QWidget,
                             QGridLayout,
                             QLabel,
                             QTableWidget,
                             QTableWidgetItem,
                             QFileDialog,
                             QSpinBox,
                             QTabWidget,
                             QVBoxLayout,
                             QStackedLayout,
                             QScrollArea,
                             QSizePolicy,
                             QMessageBox,
                             QToolButton,
                             QDialog,
                             QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
import csv
import os
import glob
import random
import datetime
from math import ceil, floor

TABLE_COLUMNS = ["Name", "Total Practice Time (min)", "Date Added", "Last Practiced", "Proficiency"]
EXTENSIONS = ["png", "jpg", "jpeg", "pdf"]

executable_dir = os.path.dirname(os.path.abspath(__file__))
folder_name = "data"
output_folder_path = os.path.join(executable_dir, folder_name)
os.makedirs(output_folder_path, exist_ok=True)


def generate_csv(index):
    file_name = f"data_{index}.csv"
    file_path = os.path.join(output_folder_path, file_name)
    with open(file_path, "a", newline="") as csv_file:
        pass
    return file_path


def save_csv(file_path, data):
    with open(file_path, "w", newline="") as csv_file:
        fieldnames = data[0].keys()
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)


def custom_sort_key(item):
    key = (item[1], random.random())
    return key


def interval_split(pieces, time):
    total_priority = sum(piece[1] for piece in pieces)
    num_pieces = len(pieces)
    piece_time_list = []
    for i in range(num_pieces):
        piece_priority = pieces[i][1]
        if i == num_pieces - 1:
            allocated_time = time
        else:
            allocated_time = round((piece_priority / total_priority) * time)
            if allocated_time < 10:
                allocated_time = 10
        piece_time_list.append(allocated_time)
        time -= allocated_time
        total_priority -= piece_priority
    return piece_time_list


def select_pieces(pieces, num_pieces, time):
    priorities = [assess_priority(piece) for piece in pieces]
    combined = list(zip(pieces, priorities))
    sorted_pieces = sorted(combined, key=custom_sort_key)
    selected_pieces = sorted_pieces[-num_pieces:]
    practice_time_list = interval_split(selected_pieces, time)
    return [{"Name": selected_pieces[i][0]["Name"], "Time": practice_time_list[i]}
            for i in range(num_pieces)]


def assess_priority(piece):
    priority = 1
    if piece["Last Practiced"] == "Never":
        priority = 4
    elif datetime.datetime.now() - datetime.datetime.strptime(piece["Last Practiced"], "%d-%m-%Y") > \
            datetime.timedelta(days=2):
        if float(piece["Total Practice Time (min)"]) < 1200:
            priority = 3
        else:
            priority = 2
    priority /= int(piece["Proficiency"])
    return priority


def session_timer_text(time):
    if time > 60:
        return f"{time // 60} h {time % 60} min"
    return f"{time} min"


def piece_timer_text(time):
    if time > 3600:
        if ceil((time % 3600) / 60) == 60:
            return f"{ceil(time / 3600)} h"
        return f"{time // 3600} h {ceil((time % 3600) / 60)} min"
    elif time < 60:
        return f"{time} s"
    return f"{time // 60} min {time % 60} s"


def checkData(row):
    name = row["Name"]
    invalid = False
    for key, value in row.items():
        if key == "Name":
            extension = value.split(".")[-1]
            if extension not in EXTENSIONS:
                popMessageBox("Invalid file extension", f"The file {name} contains an unsupported "
                                                        f"extension and will be removed.")
                return None, True
        elif key == "Total Practice Time (min)":
            try:
                time = int(value)
                if time < 0:
                    raise ValueError
            except ValueError:
                popMessageBox("Invalid value", f"{name} contains an invalid value at column '{key}': '{value}'."
                                               f"\n The value will be reset to the default value.")
                row[key] = '0'
                invalid = True
        elif key == "Last Practiced" or key == "Date Added":
            if key == "Last Practiced" and value == "Never":
                continue
            try:
                _ = datetime.datetime.strptime(value, "%d-%m-%Y")
            except ValueError:
                popMessageBox("Invalid value", f"{name} contains an invalid value at column '{key}': '{value}'."
                                               f"\n The value will be reset to the default value.")
                if key == "Date Added":
                    row[key] = datetime.datetime.now().strftime("%d-%m-%Y")
                else:
                    row[key] = "Never"
                invalid = True
        else:
            try:
                proficiency = int(value)
                if proficiency < 1 or proficiency > 10:
                    raise ValueError
            except ValueError:
                popMessageBox("Invalid value", f"{name} contains an invalid value at column '{key}': '{value}'."
                                               f"\n The value will be reset to the default value.")
                row[key] = "1"
                invalid = True
    return row, invalid


def popMessageBox(title, text):
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


class CorruptedDataDialog(QDialog):
    def __init__(self, tab_name):
        super().__init__()

        self.setWindowTitle("Warning!")

        button_box = QDialogButtonBox.StandardButton.Ok

        self.buttonBox = QDialogButtonBox(button_box)
        self.buttonBox.accepted.connect(self.accept)

        self.layout = QVBoxLayout()
        message = QLabel(f"Data is corrupted, unable to load data for {tab_name}.")
        self.layout.addWidget(message)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class Tab(QWidget):
    def __init__(self, csv_file_path, name):
        super().__init__()
        self.name = name
        self.csv_file_path = csv_file_path
        self.data = []
        self.session_pieces = []
        self.piece_display_name = None
        self.remaining_session_time = 0
        self.remaining_piece_time = 0
        self.session_timer = QTimer()
        self.session_timer.setInterval(60000)
        self.session_timer.timeout.connect(self.sessionCountdown)
        self.piece_timer = QTimer()
        self.piece_timer.setInterval(1000)
        self.piece_timer.timeout.connect(self.pieceCountdown)

        self.save_changes_button = QPushButton("Save changes")
        self.save_changes_button.setDisabled(True)
        self.delete_button = QPushButton("Delete Piece")
        self.delete_button.setDisabled(True)
        self.pause_button = QPushButton("Pause")
        self.session_time_label = QLabel()
        self.session_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.piece_time_label = QLabel()
        self.piece_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        session_timer_font = QFont()
        piece_timer_font = QFont()
        session_timer_font.setPointSize(20)
        piece_timer_font.setPointSize(16)
        self.session_time_label.setFont(session_timer_font)
        self.piece_time_label.setFont(piece_timer_font)
        self.time_spinbox = QSpinBox()
        self.time_spinbox.setRange(10, 300)
        self.time_spinbox.setSingleStep(10)
        self.time_spinbox.setValue(30)
        self.time_spinbox.valueChanged.connect(self.setNumPiecesRange)
        self.num_pieces_spinbox = QSpinBox()
        self.setNumPiecesRange()

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.setColumnWidth(0, 500)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 250)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setHighlightSections(False)

        self.display_stacked_layout = QStackedLayout()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.display_stacked_layout.addWidget(self.scroll_area)
        self.web_view = QWebEngineView()
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, True)
        self.display_stacked_layout.addWidget(self.web_view)

        self.stacked_layout = QStackedLayout()

        self.initUI()

        self.loadData()
        self.populateTable()
        self.table.itemSelectionChanged.connect(self.handleSelectionChanged)
        self.table.itemChanged.connect(self.proficiencyEdit)

    def initUI(self):
        main_layout = QGridLayout()
        study_layout = QGridLayout()

        add_file_button = QPushButton("Add file")
        start_button = QPushButton("Start session")
        start_button.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding))
        stop_button = QPushButton("Stop")
        skip_button = QPushButton("Skip")

        practice_time_label = QLabel("Practicing time (min)")
        num_pieces_label = QLabel("Number of pieces")

        add_file_button.clicked.connect(self.addFile)
        self.save_changes_button.clicked.connect(self.saveChanges)
        self.delete_button.clicked.connect(self.deletePieces)
        start_button.clicked.connect(self.startSession)
        self.pause_button.clicked.connect(self.pauseResumeSession)
        stop_button.clicked.connect(self.stopSession)
        skip_button.clicked.connect(self.skipPiece)

        main_layout.addWidget(add_file_button, 0, 1, 1, 1)
        main_layout.addWidget(self.save_changes_button, 0, 2, 1, 1)
        main_layout.addWidget(self.delete_button, 0, 3, 1, 1)
        main_layout.addWidget(self.table, 1, 0, 4, 5)
        main_layout.addWidget(practice_time_label, 5, 0, 1, 2)
        main_layout.addWidget(num_pieces_label, 5, 2, 1, 2)
        main_layout.addWidget(start_button, 5, 4, 2, 1)
        main_layout.addWidget(self.time_spinbox, 6, 0, 1, 2)
        main_layout.addWidget(self.num_pieces_spinbox, 6, 2, 1, 2)

        study_layout.addWidget(self.piece_time_label, 0, 0, 1, 5)
        study_layout.addLayout(self.display_stacked_layout, 1, 0, 4, 5)
        study_layout.addWidget(self.session_time_label, 5, 0, 3, 3)
        study_layout.addWidget(self.pause_button, 5, 4, 1, 1)
        study_layout.addWidget(stop_button, 6, 4, 1, 1)
        study_layout.addWidget(skip_button, 7, 4, 1, 1)
        for i in range(1, 5):
            main_layout.setRowStretch(i, 1)
            study_layout.setRowStretch(i, 1)

        main_screen = QWidget()
        main_screen.setLayout(main_layout)
        study_screen = QWidget()
        study_screen.setLayout(study_layout)

        self.stacked_layout.addWidget(main_screen)
        self.stacked_layout.addWidget(study_screen)
        self.setLayout(self.stacked_layout)

    def loadData(self):
        save_changes = False
        with open(self.csv_file_path, mode='r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            column_names = csv_reader.fieldnames
            if column_names == TABLE_COLUMNS:
                for row in csv_reader:
                    row, invalid = checkData(row)
                    if invalid:
                        save_changes = True
                    if row:
                        self.data.append(row)
            elif not column_names:
                pass
            else:
                dialog = CorruptedDataDialog(self.name)
                dialog.exec()
        if save_changes:
            self.saveChanges()

    def populateTable(self):
        for piece in self.data:
            self.addTableItem(piece)

    def setNumPiecesRange(self):
        # 10 min per piece at least
        total_pieces = len(self.data)
        max_num_pieces = int(self.time_spinbox.value()/10)
        self.num_pieces_spinbox.setRange(1, max_num_pieces if total_pieces > max_num_pieces else total_pieces)

    def addTableItem(self, piece):
        column = 0
        table_rows = self.table.rowCount()
        self.table.setRowCount(table_rows + 1)
        for column_name in TABLE_COLUMNS:
            entry = piece[column_name]
            if column_name == "Name":
                entry = entry.split("/")[-1].split(".")[0]
            new_item = QTableWidgetItem(entry)
            self.table.setItem(table_rows, column, new_item)
            if column_name != "Proficiency":
                self.table.item(table_rows, column).setFlags(self.table.item(table_rows, column).flags()
                                                             & ~Qt.ItemFlag.ItemIsEditable)
            column += 1

    def addFile(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Upload file", "", "Image, PDF (*.jpg *.png *.jpeg *.pdf)")
        files = [piece["Name"] for piece in self.data]
        if file_path:
            if file_path.split(".")[-1] not in EXTENSIONS:
                popMessageBox("Invalid File", "Invalid file format!")
            elif file_path not in files:
                piece_data = {
                    "Name": file_path,
                    "Total Practice Time (min)": "0",
                    "Date Added": datetime.datetime.now().strftime("%d-%m-%Y"),
                    "Last Practiced": "Never",
                    "Proficiency": "1"
                }
                self.data.append(piece_data)
                self.table.itemChanged.disconnect(self.proficiencyEdit)
                self.addTableItem(piece_data)
                self.table.itemChanged.connect(self.proficiencyEdit)
                self.save_changes_button.setDisabled(False)
                self.setNumPiecesRange()
            else:
                popMessageBox("Invalid File", "This file has already been uploaded!")

    def saveChanges(self):
        save_csv(self.csv_file_path, self.data)
        self.save_changes_button.setDisabled(True)

    def deletePieces(self):
        selected_rows = [index.row() for index in self.table.selectionModel().selectedRows()]
        for index in selected_rows:
            self.data.pop(index)
        for selected_row in reversed(selected_rows):
            self.table.removeRow(selected_row)
        self.save_changes_button.setDisabled(False)
        self.setNumPiecesRange()

    def proficiencyEdit(self, item: QTableWidgetItem):
        text = item.text()
        try:
            new_proficiency = int(text)
            if new_proficiency < 1 or new_proficiency > 10:
                raise ValueError
        except ValueError:
            popMessageBox("Invalid value", "Please provide a number with a valid value (1-10)")
            item.setText("1")
        else:
            self.data[item.row()]["Proficiency"] = str(new_proficiency)
            self.save_changes_button.setDisabled(False)

    def startSession(self):
        self.saveChanges()
        self.stacked_layout.setCurrentIndex(1)
        self.remaining_session_time = self.time_spinbox.value()
        self.session_pieces = select_pieces(self.data,
                                            self.num_pieces_spinbox.value(),
                                            self.remaining_session_time)
        self.remaining_piece_time = self.currentPiece()["Time"] * 60
        self.piece_display_name = self.currentPieceName()
        self.session_time_label.setText(session_timer_text(self.remaining_session_time))
        self.session_timer.start()
        self.piece_timer.start()
        self.updateDisplayedFile()

    def sessionCountdown(self):
        self.remaining_session_time -= 1
        self.session_time_label.setText(session_timer_text(self.remaining_session_time))
        if self.remaining_session_time == 0:
            self.session_timer.stop()

    def pieceCountdown(self):
        self.remaining_piece_time -= 1
        self.piece_time_label.setText(f"{self.piece_display_name}, "
                                      f"remaining time: {piece_timer_text(self.remaining_piece_time)}.")
        if self.remaining_piece_time == 0:
            self.updatePiece()
            self.session_pieces.pop(0)
            if self.session_pieces:
                self.remaining_piece_time = self.currentPiece()['Time'] * 60
                self.piece_display_name = self.currentPieceName()
                self.updateDisplayedFile()
            else:
                self.piece_timer.stop()
                self.onSessionFinished()

    def pauseResumeSession(self):
        if self.session_timer.isActive():
            self.session_timer.stop()
            self.piece_timer.stop()
            self.pause_button.setText("Resume")
        else:
            self.session_timer.start()
            self.piece_timer.start()
            self.pause_button.setText("Pause")

    def stopSession(self):
        self.session_timer.stop()
        self.piece_timer.stop()
        self.pause_button.setText("Pause")
        if self.session_pieces:
            self.updatePiece()
        self.onSessionFinished()

    def skipPiece(self):
        self.updatePiece()
        self.session_pieces.pop(0)
        if self.session_pieces:
            self.remaining_session_time -= ceil(self.remaining_piece_time / 60)
            self.session_time_label.setText(session_timer_text(self.remaining_session_time))
            self.remaining_piece_time = self.currentPiece()['Time'] * 60
            self.piece_display_name = self.currentPieceName()
            self.updateDisplayedFile()
        else:
            self.stopSession()

    def onSessionFinished(self):
        self.session_time_label.setText("")
        self.piece_time_label.setText("")
        self.saveChanges()
        self.updateTable()
        self.stacked_layout.setCurrentIndex(0)

    def updateTable(self):
        self.table.itemChanged.disconnect(self.proficiencyEdit)
        self.table.clearContents()
        self.table.setRowCount(0)
        self.populateTable()
        self.table.itemChanged.connect(self.proficiencyEdit)

    def updatePiece(self):
        for piece in self.data:
            if piece['Name'] == self.currentPiece()['Name']:
                practice_time = int(piece['Total Practice Time (min)']) + self.currentPiece()['Time'] \
                                - floor(self.remaining_piece_time / 60)
                piece['Total Practice Time (min)'] = f"{practice_time}"
                piece['Last Practiced'] = datetime.datetime.now().strftime("%d-%m-%Y")
                break

    def handleSelectionChanged(self):
        selected_rows = self.table.selectedItems()
        if selected_rows:
            if not self.delete_button.isEnabled():
                self.delete_button.setDisabled(False)
            if len(selected_rows) == 5:
                self.delete_button.setText("Delete Piece")
            else:
                self.delete_button.setText("Delete Pieces")
        else:
            self.delete_button.setDisabled(True)

    def currentPiece(self):
        return self.session_pieces[0]

    def currentPieceName(self):
        return self.currentPiece()["Name"].split("/")[-1].split('.')[0]

    def updateDisplayedFile(self):
        label = self.scroll_area.findChild(QLabel)
        if label:
            label.setParent(None)
        piece = self.currentPiece()["Name"]
        extension = piece.split(".")[1]
        if extension == "pdf":
            self.display_stacked_layout.setCurrentIndex(1)
            self.web_view.setUrl(QUrl(piece))
        else:
            image_label = QLabel()
            pixmap = QPixmap(piece)
            if pixmap.width() == 0:
                image_label.setText("Unable to load file.")
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                new_width = self.scroll_area.width()
                new_height = pixmap.height() * new_width // pixmap.width()
                pixmap = pixmap.scaled(new_width,
                                       new_height,
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                image_label.setPixmap(pixmap)
            self.scroll_area.setWidget(image_label)
            self.display_stacked_layout.setCurrentIndex(0)


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tab_number = 0
        self.setWindowTitle("Music Practice Automator")
        self.setMinimumSize(1500, 700)
        self.tab_widget = QTabWidget()
        self.range = [i for i in range(1, 21)]

        self.tab_button = QToolButton()
        self.tab_button.setText('+')
        self.tab_button.font().setBold(True)
        self.tab_widget.setCornerWidget(self.tab_button, corner=Qt.Corner.TopLeftCorner)
        self.tab_button.clicked.connect(self.addNewTab)

        self.init_ui()

    def init_ui(self):
        self.setCentralWidget(self.tab_widget)
        self.showMaximized()
        pattern = os.path.join(output_folder_path, 'data_*.csv')
        matching_files = glob.glob(pattern)
        if len(matching_files) == 0:
            self.addNewTab()
        else:
            for file in matching_files:
                self.addNewTab(file)

    def addNewTab(self, file_name=None):
        if not self.range:
            return
        if file_name:
            number = int(file_name.split(".")[0].split("_")[-1])
        else:
            number = self.range[0]
        self.range.remove(number)
        tab_name = f"Tab {number}"
        new_tab = Tab(generate_csv(number), tab_name)
        self.tab_widget.addTab(new_tab, tab_name)


if __name__ == "__main__":
    main_event_thread = QApplication(sys.argv)
    window = MainApp()
    sys.exit(main_event_thread.exec())
