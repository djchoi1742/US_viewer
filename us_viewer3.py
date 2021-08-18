import os
import sys
import glob
import re
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import PyQt5.QtWidgets as Qw
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

import pydicom as dcm
import pydicom.uid
import numpy as np
import timeit

menu_font = ('Helvetica', 12)
base_font = ('Helvetica', 12)
cond_interval = 23

widget_width = 1200
widget_height = int(widget_width * (2 / 3))

fig_width, fig_height = 8, 6

btn_w, btn_h, rbtn_h = 130, 25, 30
rgb_w = 85
rgb_bw = 30
type_w = 85
count_w, window_w = 40, 58


def threshold_process(line_edit):
    threshold = line_edit.text()
    threshold = int(threshold)
    if threshold < 0:
        threshold = 0
    elif threshold > 255:
        threshold = 255
    line_edit.setText(str(threshold))
    return threshold


def extract_rgb(pixel, rgb_index, direction, threshold):
    if direction:
        criteria = pixel[rgb_index] < threshold
    else:
        criteria = pixel[rgb_index] >= threshold

    if criteria:
        pixel = 0, 0, 0
    return pixel


def extract_rgb_all(pixel, r_dir, g_dir, b_dir, r_th, g_th, b_th):
    if pixel[3]:
        if r_dir:
            r_criteria = pixel[0] >= r_th
        else:
            r_criteria = pixel[0] < r_th

        if g_dir:
            g_criteria = pixel[1] >= g_th
        else:
            g_criteria = pixel[1] < g_th

        if b_dir:
            b_criteria = pixel[2] >= b_th
        else:
            b_criteria = pixel[2] < b_th

        if r_criteria and g_criteria and b_criteria:
            pixel = pixel
        else:
            pixel[0:3] = 0, 0, 0
    else:
        pixel = pixel
    return pixel


def extract_std_all(pixel, std):
    if pixel[3]:
        if np.std(pixel[0:3]) < std:
            pixel[0:3] = 0, 0, 0
        else:
            pixel = pixel
    else:
        pixel = pixel
    return pixel


def count_value(pixel):
    if pixel[3]:
        if np.sum(pixel[0:3]) != 0:
            count = True
        else:
            count = False
    else:
        count = False
    return count


def index_minus(num, index_total):
    if num <= 0 or num > index_total:
        num = None
    max_num = index_total
    if num != 1:
        num -= 1
    else:
        num = max_num
    return num


def index_plus(num, index_total):
    if num <= 0 or num > index_total:
        num = None
    max_num = index_total
    if num < max_num and num is not None:
        num += 1
    elif num == max_num:
        num = 1
    return num


def calc_distance(p1_x, p1_y, p2_x, p2_y):
    return np.sqrt(np.power(p2_x - p1_x, 2) + np.power(p2_y - p1_y, 2))


def mid_point(p1, p2):
    return int(abs(p2 + p1) / 2)


def create_circular_mask(h, w):
    center = (int(w / 2), int(h / 2))
    radius = min(center[0], center[1], w - center[0], h - center[1])

    Y, X = np.ogrid[:h, :w]
    dist_from_center = np.sqrt((X - center[0]) ** 2 + (Y - center[1]) ** 2)

    mask = dist_from_center <= radius
    mask = np.expand_dims(mask, axis=-1)

    return mask


def create_ellipse_mask(h, w):
    center = (int(w / 2), int(h / 2))
    y, x = np.ogrid[:h, :w]

    is_inner = ((x - center[0]) ** 2 / (w / 2.) ** 2) + ((y - center[1]) ** 2 / (h / 2.) ** 2)
    mask = is_inner <= 1
    mask = np.expand_dims(mask, axis=-1)
    return mask


class ViewerUS(Qw.QMainWindow):
    set_wd = None
    file_list, file_num = None, None
    dcm_filename = None
    file_index, slice_index = 0, 0
    dcm_path, ds, image_array = None, None, None
    dcm_slice, slice_num = None, None
    adjust_image = None
    first_load = True
    press_event, draw_event, release_event = None, None, None

    patch_set, patch_num = dict(), 0
    patch_type = dict()  # ellipse or rectangle

    ellipse_start_set, ellipse_end_set = dict(), dict()  # start anchor, end anchor in ellipse

    start_x, start_y, end_x, end_y = dict(), dict(), dict(), dict()
    ext_set = dict()

    def __init__(self):
        super(ViewerUS, self).__init__()

        load_action = Qw.QAction(QIcon('load.png'), 'Load...', self)
        load_action.setShortcut('Ctrl+O')
        load_action.setStatusTip('Load DICOM image')
        load_action.triggered.connect(self.load_image)

        exit_action = Qw.QAction(QIcon('exit.png'), 'Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.setStatusTip('Exit application')
        exit_action.triggered.connect(Qw.qApp.quit)

        about_action = Qw.QAction(QIcon('info.png'), 'About...', self)
        about_action.setShortcut('Ctrl+I')
        about_action.setStatusTip('View program information')
        about_action.triggered.connect(self.information)

        self.statusBar()

        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        file_menu = menu_bar.addMenu('&File')
        file_menu.addAction(load_action)
        file_menu.addAction(exit_action)

        info_menu = menu_bar.addMenu('&Info')
        info_menu.addAction(about_action)

        self.fig = plt.Figure(figsize=(fig_width, fig_height), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setGeometry(296, 30, 960, 720)

        self.ax = self.fig.add_subplot(1, 1, 1)
        self.ax.xaxis.set_visible(False)
        self.ax.yaxis.set_visible(False)
        self.fig.tight_layout()
        self.canvas.setParent(self)
        cnt_h = 30  # Top height

        self.file_name = Qw.QLineEdit('Filename', self)
        self.file_name.setGeometry(20, cnt_h, 265, btn_h)
        self.file_name.setReadOnly(True)
        cnt_h += 30

        self.file_label = Qw.QLabel('File info.', self)
        self.file_label.setGeometry(20, cnt_h, btn_w, btn_h)
        cnt_h += 25

        self.series_prev_btn = Qw.QPushButton('Prev series', self)
        self.series_prev_btn.setGeometry(20, cnt_h, btn_w, btn_h)
        self.series_prev_btn.setStyleSheet("background-color: rgb(100, 100, 100); color: white")
        self.series_prev_btn.clicked.connect(self.file_prev)
        self.series_prev_btn.setShortcut('Up')

        self.series_next_btn = Qw.QPushButton('Next series', self)
        self.series_next_btn.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        self.series_next_btn.setStyleSheet("background-color: rgb(100, 100, 100); color: white")
        self.series_next_btn.clicked.connect(self.file_next)
        self.series_next_btn.setShortcut('Down')
        cnt_h += 30

        self.slice_label = Qw.QLabel('Slice info.', self)
        self.slice_label.setGeometry(20, cnt_h, 110, btn_h)  # (int x, int y, int w, int h)
        cnt_h += 25

        self.slice_prev_btn = Qw.QPushButton('Prev slice', self)
        self.slice_prev_btn.setGeometry(20, cnt_h, btn_w, btn_h)  # (x, y, w, h)
        self.slice_prev_btn.setStyleSheet("background-color: rgb(140, 140, 140); color: white")
        self.slice_prev_btn.clicked.connect(self.slice_prev)
        self.slice_prev_btn.setShortcut('Left')

        self.slice_next_btn = Qw.QPushButton('Next slice', self)
        self.slice_next_btn.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        self.slice_next_btn.setStyleSheet("background-color: rgb(140, 140, 140); color: white")
        self.slice_next_btn.clicked.connect(self.slice_next)
        self.slice_next_btn.setShortcut('Right')
        cnt_h += 35

        self.coord_label = Qw.QLabel('Show Coordinates:', self)
        self.coord_label.setGeometry(20, cnt_h, 200, btn_h)
        cnt_h += 25

        self.draw_type = Qw.QLabel('Draw Type', self)
        self.draw_type.setGeometry(20, cnt_h, 200, btn_h)
        cnt_h += 20

        type_group = Qw.QButtonGroup(self)

        self.draw_ellipse = Qw.QRadioButton('Ellipse', self)
        type_group.addButton(self.draw_ellipse)
        self.draw_ellipse.setGeometry(20, cnt_h, type_w, btn_h)
        self.draw_ellipse.setChecked(True)
        self.draw_ellipse.clicked.connect(self.set_ellipse)

        self.draw_rectangle = Qw.QRadioButton('Rectangle', self)
        type_group.addButton(self.draw_rectangle)
        self.draw_rectangle.setGeometry(20 + btn_w + 5, cnt_h, type_w, btn_h)
        self.draw_rectangle.clicked.connect(self.set_rectangle)
        cnt_h += 25

        self.draw_mode = Qw.QLabel('Draw Mode', self)
        self.draw_mode.setGeometry(20, cnt_h, 200, btn_h)
        cnt_h += 20

        mode_group = Qw.QButtonGroup(self)

        self.draw_mode_h = Qw.QRadioButton('Hand', self)
        mode_group.addButton(self.draw_mode_h)
        self.draw_mode_h.setGeometry(20, cnt_h, 100, btn_h)
        self.draw_mode_h.setChecked(True)

        self.draw_mode_l = Qw.QRadioButton('Length setting', self)
        mode_group.addButton(self.draw_mode_l)
        self.draw_mode_l.setGeometry(20 + btn_w + 5, cnt_h, 100, btn_h)
        cnt_h += 28

        self.adj_h_label = Qw.QLabel('Adjust Height', self)
        self.adj_h_label.setGeometry(20, cnt_h, btn_w, btn_h)

        self.adj_w_label = Qw.QLabel('Adjust Width', self)
        self.adj_w_label.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 25

        self.adj_h_edit = Qw.QLineEdit('80', self)
        self.adj_h_edit.setGeometry(20, cnt_h, btn_w, btn_h)

        self.adj_w_edit = Qw.QLineEdit('80', self)
        self.adj_w_edit.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 35

        self.region_label = Qw.QLabel('**Selected Region**', self)
        self.region_label.setGeometry(20, cnt_h, 200, btn_h)
        cnt_h += 20

        self.region_lt = Qw.QLabel('Left Top', self)
        self.region_lt.setGeometry(20, cnt_h, btn_w, btn_h)

        self.region_rb = Qw.QLabel('Right Bottom', self)
        self.region_rb.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 25

        self.region_lt_value = Qw.QLineEdit(self)
        self.region_lt_value.setGeometry(20, cnt_h, btn_w, btn_h)

        self.region_rb_value = Qw.QLineEdit(self)
        self.region_rb_value.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 28

        self.cnt_h_label = Qw.QLabel('Current Height', self)
        self.cnt_h_label.setGeometry(20, cnt_h, btn_w, btn_h)

        self.cnt_w_label = Qw.QLabel('Current Width', self)
        self.cnt_w_label.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 25

        self.cnt_h_value = Qw.QLineEdit(self)
        self.cnt_h_value.setGeometry(20, cnt_h, btn_w, btn_h)
        self.cnt_h_value.setReadOnly(True)

        self.cnt_w_value = Qw.QLineEdit(self)
        self.cnt_w_value.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        self.cnt_w_value.setReadOnly(True)
        cnt_h += 35

        extract_group = Qw.QButtonGroup(self)
        self.extract_rgb = Qw.QRadioButton('Extract to RGB', self)
        self.extract_rgb.setChecked(True)
        extract_group.addButton(self.extract_rgb)
        self.extract_rgb.setGeometry(20, cnt_h, btn_w, btn_h)
        cnt_h += 25

        cnt_w = 0
        self.label_r = Qw.QLabel('Red', self)
        self.label_r.setGeometry(20, cnt_h, rgb_w, btn_h)
        self.label_r.setAlignment(Qt.AlignCenter)
        self.label_r.setStyleSheet('background-color: red; color: white')

        cnt_w += rgb_w + 5
        self.label_g = Qw.QLabel('Green', self)
        self.label_g.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.label_g.setAlignment(Qt.AlignCenter)
        self.label_g.setStyleSheet('background-color: green; color: white')

        cnt_w += rgb_w + 5
        self.label_b = Qw.QLabel('Blue', self)
        self.label_b.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.label_b.setAlignment(Qt.AlignCenter)
        self.label_b.setStyleSheet('background-color: blue; color: white')

        cnt_h += 32

        cnt_w = 0
        group_layout1 = Qw.QHBoxLayout(self)

        group_r1 = Qw.QGroupBox(self)
        group_r1.setGeometry(20, cnt_h, rgb_w, rbtn_h)
        group_layout1.addWidget(group_r1)
        group_r1_layout = Qw.QHBoxLayout()
        group_r1.setLayout(group_r1_layout)
        self.radio_r1_more = Qw.QRadioButton('>')
        self.radio_r1_more.setGeometry(20, cnt_h, rgb_bw, rbtn_h)
        self.radio_r1_more.setChecked(True)
        self.radio_r1_less = Qw.QRadioButton('<')
        self.radio_r1_less.setGeometry(20 + rgb_bw + 5, cnt_h, rgb_bw, rbtn_h)
        group_r1_layout.addWidget(self.radio_r1_more)
        group_r1_layout.addWidget(self.radio_r1_less)

        cnt_w += rgb_w + 5
        group_g1 = Qw.QGroupBox(self)
        group_g1.setGeometry(20 + cnt_w, cnt_h, rgb_w, rbtn_h)
        group_layout1.addWidget(group_g1)
        group_g1_layout = Qw.QHBoxLayout()
        group_g1.setLayout(group_g1_layout)
        self.radio_g1_more = Qw.QRadioButton('>')
        self.radio_g1_more.setGeometry(20 + cnt_w, cnt_h, rgb_bw, rbtn_h)
        self.radio_g1_less = Qw.QRadioButton('<')
        self.radio_g1_less.setGeometry(20 + cnt_w + rgb_bw + 5, cnt_h, rgb_bw, rbtn_h)
        self.radio_g1_less.setChecked(True)
        group_g1_layout.addWidget(self.radio_g1_more)
        group_g1_layout.addWidget(self.radio_g1_less)

        cnt_w += rgb_w + 5
        group_b1 = Qw.QGroupBox(self)
        group_b1.setGeometry(20 + cnt_w, cnt_h, rgb_w, rbtn_h)
        group_layout1.addWidget(group_b1)
        group_b1_layout = Qw.QHBoxLayout()
        group_b1.setLayout(group_b1_layout)
        self.radio_b1_more = Qw.QRadioButton('>')
        self.radio_b1_more.setGeometry(20 + cnt_w, cnt_h, rgb_bw, rbtn_h)
        self.radio_b1_more.setChecked(True)
        self.radio_b1_less = Qw.QRadioButton('<')
        self.radio_b1_less.setGeometry(20 + cnt_w + rgb_bw + 5, cnt_h, rgb_bw, rbtn_h)
        group_b1_layout.addWidget(self.radio_b1_more)
        group_b1_layout.addWidget(self.radio_b1_less)
        cnt_h += 32

        cnt_w = 0
        self.value_r1 = Qw.QLineEdit(self)
        self.value_r1.setGeometry(20, cnt_h, rgb_w, btn_h)
        self.value_r1.setText('128')
        self.value_r1.setReadOnly(False)

        cnt_w += rgb_w + 5
        self.value_g1 = Qw.QLineEdit(self)
        self.value_g1.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.value_g1.setText('128')
        self.value_g1.setReadOnly(False)

        cnt_w += rgb_w + 5
        self.value_b1 = Qw.QLineEdit(self)
        self.value_b1.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.value_b1.setText('128')
        self.value_b1.setReadOnly(False)
        cnt_h += 32

        # 2nd layout or std extract
        self.extract_std = Qw.QRadioButton('Extract to Stdev', self)
        extract_group.addButton(self.extract_std)
        self.extract_std.setGeometry(20, cnt_h, btn_w, btn_h)

        self.edit_std = Qw.QLineEdit('40', self)
        self.edit_std.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 30

        self.extract_btn = Qw.QPushButton('Pixel Extract', self)
        self.extract_btn.setGeometry(20, cnt_h, 265, btn_h)
        self.extract_btn.setStyleSheet("background-color: rgb(170, 170, 170); color: white")
        # self.extract_btn.clicked.connect(lambda: self.extract_pixel(self.count_window))
        self.extract_btn.clicked.connect(self.extract_pixel)
        self.extract_btn.setShortcut('Alt+s')
        cnt_h += 32

        self.count_label = Qw.QLabel('Count: ', self)
        self.count_label.setGeometry(20, cnt_h, btn_w, btn_h)
        self.count_label.setAlignment(Qt.AlignCenter)

        self.count_window = Qw.QLineEdit(self)
        self.count_window.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        self.count_window.setReadOnly(True)
        cnt_h += 40

        self.set_default = Qw.QPushButton('Initialize', self)
        self.set_default.setGeometry(20, cnt_h, btn_w, btn_h)
        self.set_default.clicked.connect(self.default_image)
        self.set_default.setShortcut('Alt+d')

        self.statusBar().showMessage('Ready')

    def load_image(self):
        self.set_wd = Qw.QFileDialog.getExistingDirectory(self, 'Open Folder', self.set_wd)

        if self.set_wd == '':
            return
        else:
            self.file_list = glob.glob(os.path.join(self.set_wd + '/*.dcm'))

            if len(self.file_list) > 0:
                self.file_num = len(self.file_list)
                self.file_index, self.slice_index = 1, 1

                self.dcm_path = self.file_list[self.file_index - 1]
                self.ds = dcm.read_file(self.dcm_path)

                self.dcm_filename = os.path.basename(self.dcm_path)
                self.image_array = self.ds.pixel_array
                self.slice_num = self.image_array.shape[0]
                self.view_image('slice')

                self.file_label.setText('%d/%d' % (self.file_index, self.file_num))
                self.file_name.setText(self.dcm_filename)

            else:
                self.popup_box("Error!", "Select the folder that contains DICOM file in video format.")

    def view_image(self, index_type):
        if index_type == 'file':
            self.dcm_path = self.file_list[self.file_index - 1]
            self.ds = dcm.read_file(self.dcm_path)

            self.dcm_filename = os.path.basename(self.dcm_path)
            self.image_array = self.ds.pixel_array
            self.slice_num = self.image_array.shape[0]

            if self.slice_index > self.slice_num:
                self.slice_index = self.slice_num
            self.dcm_slice = self.image_array[self.slice_index - 1]
            self.file_name.setText(self.dcm_filename)
            self.default_patch()

        elif index_type == 'slice':
            self.dcm_slice = self.image_array[self.slice_index - 1]
            self.default_patch()

        else:
            raise ValueError('Error! Invalid index type.')

        if self.first_load:
            self.ax.imshow(self.dcm_slice)
            self.canvas.draw()

            self.canvas.callbacks.connect('motion_notify_event', self.motion_coord)

            if self.draw_ellipse.isChecked():
                self.press_event = self.canvas.callbacks.connect('button_press_event', self.ellipse_press)
                self.draw_event = self.canvas.callbacks.connect('motion_notify_event', self.ellipse_draw)
                self.release_event = self.canvas.callbacks.connect('button_release_event', self.ellipse_release)

            self.canvas.callbacks.connect('button_press_event', self.patch_remove)

            self.first_load = False
        else:
            self.ax.clear()
            self.ax.imshow(self.dcm_slice)
            self.canvas.draw()

        self.file_label.setText('%d/%d' % (self.file_index, self.file_num))
        self.slice_label.setText('%d/%d' % (self.slice_index, self.slice_num))

        self.count_window.setText('')

        self.statusBar().showMessage('Image upload')

    def set_rectangle(self):
        self.canvas.callbacks.disconnect(self.press_event)
        self.canvas.callbacks.disconnect(self.draw_event)
        self.canvas.callbacks.disconnect(self.release_event)
        self.press_event = self.canvas.callbacks.connect('button_press_event', self.rect_press)
        self.draw_event = self.canvas.callbacks.connect('motion_notify_event', self.rect_draw)
        self.release_event = self.canvas.callbacks.connect('button_release_event', self.rect_release)

    def set_ellipse(self):
        self.canvas.callbacks.disconnect(self.press_event)
        self.canvas.callbacks.disconnect(self.draw_event)
        self.canvas.callbacks.disconnect(self.release_event)
        self.press_event = self.canvas.callbacks.connect('button_press_event', self.ellipse_press)
        self.draw_event = self.canvas.callbacks.connect('motion_notify_event', self.ellipse_draw)
        self.release_event = self.canvas.callbacks.connect('button_release_event', self.ellipse_release)

    def patch_load(self):
        for idx in range(1, self.patch_num + 1):
            self.ax.add_patch(self.patch_set[idx])

    def default_patch(self):
        if self.patch_num > 0:
            cnt_patch = self.patch_num
            for idx in range(1, cnt_patch + 1):
                self.start_x.pop(idx)
                self.start_y.pop(idx)
                self.end_x.pop(idx)
                self.end_y.pop(idx)
                self.ext_set.pop(idx)
                self.patch_set.pop(idx)

                if self.patch_type[idx] == 'ellipse':
                    self.ellipse_start_set.pop(idx)
                    self.ellipse_end_set.pop(idx)
                self.patch_num -= 1
        else:
            return

    def default_image(self):
        if self.first_load is False:
            if self.patch_num > 0:
                self.default_patch()
                self.ax.clear()
                self.ax.imshow(self.dcm_slice)
                self.canvas.draw()
                self.statusBar().showMessage('Default image')
            else:
                self.popup_box('Error!', 'No region was marked.')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def motion_coord(self, event):
        if event.inaxes is not None:
            if int(event.xdata) < self.dcm_slice.shape[1] and int(event.ydata) < self.dcm_slice.shape[0]:
                m_r, m_g, m_b = self.dcm_slice[int(event.ydata), int(event.xdata),]
                motion_text = 'X: %d, Y: %d' % (int(event.xdata), int(event.ydata))

                value_text = 'Val: %d, %d, %d' % (m_r, m_g, m_b)
                total_text = motion_text + '  ' + value_text
                self.coord_label.setText(total_text)
            else:
                return
        else:
            return

    def cnt_anchor(self, start_x, start_y, end_x, end_y, hw_edit=False):
        region_lt = 'X: %d, Y: %d' % (min(start_x, end_x), min(start_y, end_y))
        region_rb = 'X: %d, Y: %d' % (max(start_x, end_x), max(start_y, end_y))
        current_height = str(abs(start_y - end_y))
        current_width = str(abs(start_x - end_x))

        self.region_lt_value.setText(region_lt)
        self.region_rb_value.setText(region_rb)
        self.cnt_h_value.setText(current_height)
        self.cnt_w_value.setText(current_width)

        if hw_edit:
            self.adj_h_edit.setText(current_height)
            self.adj_w_edit.setText(current_width)

    def ellipse_gen(self, event):
        if event.inaxes is not None and event.button == 1:
            try:
                h, w = int(self.adj_h_edit.text()), int(self.adj_w_edit.text())
            except:
                self.popup_box('Error!', 'Please enter a valid integer.')
                return

            idx = self.patch_num + 1

            self.start_x[idx], self.start_y[idx] = int(event.xdata), int(event.ydata)
            self.ellipse_start_set[idx] = patches.Circle(xy=(self.start_x[idx], self.start_y[idx]),
                                                         radius=1, fill=False, color='ivory')
            self.ax.add_patch(self.ellipse_start_set[idx])

            center_x = int((self.start_x[idx] * 2 + w) / 2)
            center_y = int((self.start_y[idx] * 2 + h) / 2)
            self.patch_set[idx] = patches.Ellipse(xy=(center_x, center_y), width=w, height=h,
                                                  fill=False, color='gold')
            self.ax.add_patch(self.patch_set[idx])

            self.end_x[idx], self.end_y[idx] = self.start_x[idx] + w, self.start_y[idx] + h
            self.ellipse_end_set[idx] = patches.Circle(xy=(self.end_x[idx], self.end_y[idx]),
                                                       radius=1, fill=False, color='ivory')
            self.ax.add_patch(self.ellipse_end_set[idx])
            self.canvas.draw()

            self.cnt_h_value.setText(self.adj_h_edit.text())
            self.cnt_w_value.setText(self.adj_w_edit.text())

            self.patch_type[idx] = 'ellipse'

            self.cnt_anchor(self.start_x[idx], self.start_y[idx], self.end_x[idx], self.end_y[idx])

            self.ext_set[idx] = False
            self.patch_num += 1
        else:
            return

    def ellipse_press(self, event):
        if self.draw_mode_h.isChecked():
            if event.inaxes is not None and event.button == 1:
                idx = self.patch_num + 1
                self.start_x[idx], self.start_y[idx] = int(event.xdata), int(event.ydata)
                self.ellipse_start_set[idx] = patches.Circle(xy=(self.start_x[idx], self.start_y[idx]),
                                                             radius=1, fill=False, color='ivory')

                self.ax.add_patch(self.ellipse_start_set[idx])
                self.patch_set[idx] = patches.Ellipse(xy=(self.start_x[idx], self.start_y[idx]),
                                                      width=1, height=1, fill=False, color='gold')

                self.ax.add_patch(self.patch_set[idx])
                self.canvas.draw()
            else:
                return
        elif self.draw_mode_l.isChecked():
            self.ellipse_gen(event)

    def ellipse_draw(self, event):
        if self.draw_mode_h.isChecked():
            if event.inaxes is not None and event.button == 1:
                idx = self.patch_num + 1
                self.patch_set[idx].set_center(
                    xy=(mid_point(event.xdata, self.start_x[idx]), mid_point(event.ydata, self.start_y[idx])))

                self.patch_set[idx].set_height(1 * (int(event.ydata) - self.start_y[idx]))
                self.patch_set[idx].set_width(1 * (int(event.xdata) - self.start_x[idx]))
                self.canvas.draw()
            else:
                return
        else:
            return

    def ellipse_release(self, event):
        if self.draw_mode_h.isChecked():
            if event.inaxes is not None and event.button == 1:
                idx = self.patch_num + 1
                self.ellipse_end_set[idx] = patches.Circle(xy=(int(event.xdata), int(event.ydata)),
                                                           radius=1, fill=False, color='ivory')
                self.ax.add_patch(self.ellipse_end_set[idx])
                self.canvas.draw()

                self.end_x[idx], self.end_y[idx] = int(event.xdata), int(event.ydata)
                self.patch_type[idx] = 'ellipse'

                self.cnt_anchor(self.start_x[idx], self.start_y[idx], self.end_x[idx], self.end_y[idx], hw_edit=True)

                self.ext_set[idx] = False
                self.patch_num += 1
            else:
                return
        else:
            return

    def rect_gen(self, event):
        if event.inaxes is not None and event.button == 1:
            try:
                h, w = int(self.adj_h_edit.text()), int(self.adj_w_edit.text())
            except:
                self.popup_box('Error!', 'Please enter a valid integer.')
                return

            idx = self.patch_num + 1

            self.start_x[idx], self.start_y[idx] = int(event.xdata), int(event.ydata)
            self.patch_set[idx] = patches.Rectangle(xy=(self.start_x[idx], self.start_y[idx]),
                                                    width=w, height=h, fill=False, color='gold')
            self.ax.add_patch(self.patch_set[idx])
            self.canvas.draw()

            self.end_x[idx], self.end_y[idx] = self.start_x[idx] + w, self.start_y[idx] + h
            self.patch_type[idx] = 'rectangle'

            self.cnt_anchor(self.start_x[idx], self.start_y[idx], self.end_x[idx], self.end_y[idx])

            self.ext_set[idx] = False
            self.patch_num += 1

        else:
            return

    def rect_press(self, event):
        if self.draw_mode_h.isChecked():
            if event.inaxes is not None and event.button == 1:
                idx = self.patch_num + 1
                self.start_x[idx], self.start_y[idx] = int(event.xdata), int(event.ydata)
                self.patch_set[idx] = patches.Rectangle(xy=(self.start_x[idx], self.start_y[idx]),
                                                        width=1, height=1, fill=False, color='gold')
                self.ax.add_patch(self.patch_set[idx])
                self.canvas.draw()
            else:
                return
        else:
            self.rect_gen(event)

    def rect_draw(self, event):
        if self.draw_mode_h.isChecked():
            if event.inaxes is not None and event.button == 1:
                idx = self.patch_num + 1
                self.patch_set[idx].set_height(int(event.ydata) - self.start_y[idx])
                self.patch_set[idx].set_width(int(event.xdata) - self.start_x[idx])
                self.canvas.draw()
            else:
                return
        else:
            return

    def rect_release(self, event):
        if self.draw_mode_h.isChecked():
            if event.inaxes is not None and event.button == 1:
                idx = self.patch_num + 1
                self.end_x[idx], self.end_y[idx] = int(event.xdata), int(event.ydata)

                self.patch_type[idx] = 'rectangle'
                self.cnt_anchor(self.start_x[idx], self.start_y[idx], self.end_x[idx], self.end_y[idx], hw_edit=True)

                self.ext_set[idx] = False
                self.patch_num += 1
            else:
                return
        else:
            return

    def patch_remove(self, event):
        if event.inaxes is not None and event.button == 2:
            if self.patch_num > 0:
                self.patch_set[self.patch_num].remove()
                self.patch_set.pop(self.patch_num)

                if self.patch_type[self.patch_num] == 'ellipse':
                    self.ellipse_start_set[self.patch_num].remove()
                    self.ellipse_start_set.pop(self.patch_num)
                    self.ellipse_end_set[self.patch_num].remove()
                    self.ellipse_end_set.pop(self.patch_num)

                self.start_x.pop(self.patch_num)
                self.start_y.pop(self.patch_num)
                self.end_x.pop(self.patch_num)
                self.end_y.pop(self.patch_num)
                self.patch_type.pop(self.patch_num)

                if self.ext_set[self.patch_num]:
                    self.ax.imshow(self.dcm_slice)
                    self.ext_set.pop(self.patch_num)

                self.canvas.draw()
                self.patch_num -= 1
            else:
                self.popup_box('Error!', 'There is no region to remove.')
        else:
            return

    def extract_pixel(self):
        if self.extract_rgb.isChecked():
            self.extract_pixel_rgb(self.count_window)
        elif self.extract_std.isChecked():
            self.extract_pixel_std(self.count_window)
        else:
            raise ValueError('Error!, Invalid extract type!')

    def extract_region(self):
        zeros_image = np.zeros(self.dcm_slice.shape, dtype=self.dcm_slice.dtype)

        x1 = min(self.start_x[self.patch_num], self.end_x[self.patch_num])
        x2 = max(self.start_x[self.patch_num], self.end_x[self.patch_num])
        y1 = min(self.start_y[self.patch_num], self.end_y[self.patch_num])
        y2 = max(self.start_y[self.patch_num], self.end_y[self.patch_num])

        self.set_image = self.dcm_slice - zeros_image
        adjust_image = self.set_image.copy()

        if abs(x1 - x2) >= 2 and abs(y1 - y2) >= 2:
            if self.draw_ellipse.isChecked():
                pixel_mask = create_ellipse_mask(y2 - y1, x2 - x1)
            else:
                pixel_mask = np.expand_dims(np.ones((y2 - y1, x2 - x1), dtype=np.uint8), axis=-1)
            concat_mask = np.concatenate((adjust_image[y1:y2, x1:x2], pixel_mask), axis=-1)
        else:
            concat_mask = None

        return x1, y1, x2, y2, adjust_image, concat_mask

    def extract_result(self, adjust_image):
        self.ax.clear()
        self.ax.imshow(adjust_image)
        self.patch_load()
        self.canvas.draw()

        self.ext_set[self.patch_num] = True
        self.statusBar().showMessage('Done')

    def extract_pixel_std(self, result_window):
        if self.first_load is False:
            if self.patch_num > 0:
                x1, y1, x2, y2, adjust_image, concat_mask = self.extract_region()

                if concat_mask is not None:
                    try:
                        valid_std = float(self.edit_std.text())
                    except:
                        self.popup_box('Error!', 'Do not enter characters other than numbers.')
                        return

                    pixel_result = np.apply_along_axis(
                        lambda x: extract_std_all(x, valid_std), 2, concat_mask)
                    pixel_count = np.sum(np.apply_along_axis(count_value, 2, pixel_result))
                    result_window.setText(str(pixel_count))
                    adjust_image[y1:y2, x1:x2] = pixel_result[:, :, 0:3]
                    self.extract_result(adjust_image)
                else:
                    self.popup_box('Error!', 'Selected region is too small for analysis.')
            else:
                self.popup_box('Error!', 'Please draw desired region first.')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def extract_pixel_rgb(self, result_window):
        if self.first_load is False:
            if self.patch_num > 0:
                is_r = len(self.value_r1.text()) > 0
                is_g = len(self.value_g1.text()) > 0
                is_b = len(self.value_b1.text()) > 0

                if is_r and is_g and is_b:
                    valid_r = re.search('\D', self.value_r1.text())
                    valid_g = re.search('\D', self.value_g1.text())
                    valid_b = re.search('\D', self.value_b1.text())

                    if valid_r is None and valid_g is None and valid_b is None:
                        thres_r = threshold_process(self.value_r1)
                        thres_g = threshold_process(self.value_g1)
                        thres_b = threshold_process(self.value_b1)

                        x1, y1, x2, y2, adjust_image, concat_mask = self.extract_region()

                        if concat_mask is not None:
                            pixel_result = np.apply_along_axis(
                                lambda x: extract_rgb_all(x,
                                                          self.radio_r1_more.isChecked(),
                                                          self.radio_g1_more.isChecked(),
                                                          self.radio_b1_more.isChecked(),
                                                          thres_r, thres_g, thres_b), 2, concat_mask)

                            pixel_count = np.sum(np.apply_along_axis(count_value, 2, pixel_result))
                            result_window.setText(str(pixel_count))
                            adjust_image[y1:y2, x1:x2] = pixel_result[:, :, 0:3]
                            self.extract_result(adjust_image)
                        else:
                            self.popup_box('Error!', 'Selected region is too small for analysis.')
                    else:
                        self.popup_box('Error!', 'Do not enter characters other than numbers.')
                else:
                    self.popup_box('Error!', 'Please enter a number between 0 and 255.')
            else:
                self.popup_box('Error!', 'Please draw desired region first.')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def file_next(self):
        if self.first_load is False:
            self.file_index = index_plus(self.file_index, self.file_num)
            self.view_image('file')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def file_prev(self):
        if self.first_load is False:
            self.file_index = index_minus(self.file_index, self.file_num)
            self.view_image('file')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def slice_next(self):
        if self.first_load is False:
            self.slice_index = index_plus(self.slice_index, self.slice_num)
            self.view_image('slice')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def slice_prev(self):
        if self.first_load is False:
            self.slice_index = index_minus(self.slice_index, self.slice_num)
            self.view_image('slice')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def information(self):
        self.popup_box('Program information',
                       'Image viewer for Doppler ultrasonography v1.1\nDeveloped by Dongjun Choi')

    def popup_box(self, popup_title, popup_message):
        Qw.QMessageBox.about(self, popup_title, popup_message)

    def run_app(self):
        self.setGeometry(200, 40, widget_width + 70, widget_height + 10)
        self.setWindowTitle('US viewer v1.1')
        self.show()


if __name__ == '__main__':
    sys._excepthook = sys.excepthook

    def exception_hook(exctype, value, traceback):
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)

    sys.excepthook = exception_hook

    app = Qw.QApplication(sys.argv)
    viewer_us = ViewerUS()
    viewer_us.run_app()
    sys.exit(app.exec_())
