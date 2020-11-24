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
widget_height = int(widget_width * (2/3))

fig_width, fig_height = 8, 6


btn_w, btn_h = 130, 30
rgb_w = 85
rgb_bw = 30
count_w, window_w = 40, 58


def extract_rgb(pixel, rgb_index, direction, threshold):
    if direction:
        criteria = pixel[rgb_index] < threshold
    else:
        criteria = pixel[rgb_index] >= threshold

    if criteria:
        pixel = 0, 0, 0
    return pixel


def extract_rgb_all(pixel, r_dir, g_dir, b_dir, r_th, g_th, b_th):
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
        pixel = 0, 0, 0
    return pixel


def count_value(pixel):
    if np.sum(pixel) != 0:
        count = True
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


class ViewerUS(Qw.QMainWindow):
    set_wd = None
    file_list, file_num = None, None
    dcm_filename = None
    file_index, slice_index = 0, 0
    dcm_path, ds, image_array = None, None, None
    dcm_slice, slice_num = None, None
    adjust_image = None
    first_load = True

    rect_set, rect_num = dict(), 0

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
        cnt_h += 40

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
        cnt_h += 40

        self.coord_label = Qw.QLabel('Show coordinates:', self)
        self.coord_label.setGeometry(20, cnt_h, 200, btn_h)

        cnt_h += 30

        self.region_label = Qw.QLabel('Selected region', self)
        self.region_label.setGeometry(20, cnt_h, 200, btn_h)
        cnt_h += 25

        self.region_lt = Qw.QLabel('Left top', self)
        self.region_lt.setGeometry(20, cnt_h, btn_w, btn_h)

        self.region_rb = Qw.QLabel('Right bottom', self)
        self.region_rb.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 25

        self.region_lt_value = Qw.QLineEdit(self)
        self.region_lt_value.setGeometry(20, cnt_h, btn_w, btn_h)

        self.region_rb_value = Qw.QLineEdit(self)
        self.region_rb_value.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 30

        self.region_h = Qw.QLabel('Height', self)
        self.region_h.setGeometry(20, cnt_h, btn_w, btn_h)

        self.region_w = Qw.QLabel('Width', self)
        self.region_w.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 25

        self.region_w_value = Qw.QLineEdit(self)
        self.region_w_value.setGeometry(20, cnt_h, btn_w, btn_h)

        self.region_h_value = Qw.QLineEdit(self)
        self.region_h_value.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        cnt_h += 45

        cnt_w = 0
        self.label_r = Qw.QLabel('Red', self)
        self.label_r.setGeometry(20, cnt_h, rgb_w, btn_h)
        self.label_r.setAlignment(Qt.AlignCenter)
        self.label_r.setStyleSheet('background-color: red; color: white')
        # self.label_r.clicked.connect(lambda: self.adjust_rgb(0, self.radio_r_more.isChecked(),
        #                                                       self.value_r.text()))
        # self.label_r.setShortcut('Alt+r')

        cnt_w += rgb_w + 5
        self.label_g = Qw.QLabel('Green', self)
        self.label_g.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.label_g.setAlignment(Qt.AlignCenter)
        self.label_g.setStyleSheet('background-color: green; color: white')
        # self.label_g.clicked.connect(lambda: self.adjust_rgb(1, self.radio_g_more.isChecked(),
        #                                                       self.value_g.text()))
        # self.label_g.setShortcut('Alt+g')

        cnt_w += rgb_w + 5
        self.label_b = Qw.QLabel('Blue', self)
        self.label_b.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.label_b.setAlignment(Qt.AlignCenter)
        self.label_b.setStyleSheet('background-color: blue; color: white')
        # self.label_b.clicked.connect(lambda: self.adjust_rgb(2, self.radio_b_more.isChecked(),
        #                                                       self.value_b.text()))
        # self.label_b.setShortcut('Alt+b')
        cnt_h += 32

        cnt_w = 0

        group_layout = Qw.QHBoxLayout(self)

        group_r = Qw.QGroupBox(self)
        group_r.setGeometry(20, cnt_h, rgb_w, btn_h)
        group_layout.addWidget(group_r)
        group_r_layout = Qw.QHBoxLayout()
        group_r.setLayout(group_r_layout)
        self.radio_r_more = Qw.QRadioButton('>')
        self.radio_r_more.setGeometry(20, cnt_h, rgb_bw, btn_h)
        self.radio_r_more.setChecked(True)
        self.radio_r_less = Qw.QRadioButton('<')
        self.radio_r_less.setGeometry(20 + rgb_bw + 5, cnt_h, rgb_bw, btn_h)
        group_r_layout.addWidget(self.radio_r_more)
        group_r_layout.addWidget(self.radio_r_less)

        cnt_w += rgb_w + 5
        group_g = Qw.QGroupBox(self)
        group_g.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        group_layout.addWidget(group_g)
        group_g_layout = Qw.QHBoxLayout()
        group_g.setLayout(group_g_layout)
        self.radio_g_more = Qw.QRadioButton('>')
        self.radio_g_more.setGeometry(20 + cnt_w, cnt_h, rgb_bw, btn_h)
        self.radio_g_less = Qw.QRadioButton('<')
        self.radio_g_less.setGeometry(20 + cnt_w + rgb_bw + 5, cnt_h, rgb_bw, btn_h)
        self.radio_g_less.setChecked(True)
        group_g_layout.addWidget(self.radio_g_more)
        group_g_layout.addWidget(self.radio_g_less)

        cnt_w += rgb_w + 5
        group_b = Qw.QGroupBox(self)
        group_b.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        group_layout.addWidget(group_b)
        group_b_layout = Qw.QHBoxLayout()
        group_b.setLayout(group_b_layout)
        self.radio_b_more = Qw.QRadioButton('>')
        self.radio_b_more.setGeometry(20 + cnt_w, cnt_h, rgb_bw, btn_h)
        self.radio_b_more.setChecked(True)
        self.radio_b_less = Qw.QRadioButton('<')
        self.radio_b_less.setGeometry(20 + cnt_w + rgb_bw + 5, cnt_h, rgb_bw, btn_h)
        group_b_layout.addWidget(self.radio_b_more)
        group_b_layout.addWidget(self.radio_b_less)
        cnt_h += 32

        cnt_w = 0
        self.value_r = Qw.QLineEdit(self)
        self.value_r.setGeometry(20, cnt_h, rgb_w, btn_h)
        self.value_r.setText('128')
        self.value_r.setReadOnly(False)

        cnt_w += rgb_w + 5
        self.value_g = Qw.QLineEdit(self)
        self.value_g.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.value_g.setText('128')
        self.value_g.setReadOnly(False)

        cnt_w += rgb_w + 5
        self.value_b = Qw.QLineEdit(self)
        self.value_b.setGeometry(20 + cnt_w, cnt_h, rgb_w, btn_h)
        self.value_b.setText('128')
        self.value_b.setReadOnly(False)

        cnt_h += 32

        self.extract_btn = Qw.QPushButton('Pixel Extract', self)
        self.extract_btn.setGeometry(20, cnt_h, 265, btn_h)
        self.extract_btn.setStyleSheet("background-color: rgb(170, 170, 170); color: white")
        self.extract_btn.clicked.connect(lambda: self.extract_pixel(self.count_window))
        self.extract_btn.setShortcut('Alt+s')
        cnt_h += 32

        self.count_label = Qw.QLabel('Count: ', self)
        self.count_label.setGeometry(20, cnt_h, btn_w, btn_h)
        self.count_label.setAlignment(Qt.AlignCenter)

        self.count_window = Qw.QLineEdit(self)
        self.count_window.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
        self.count_window.setReadOnly(True)
        cnt_h += 40

        if False:
            self.extract_r_btn = Qw.QPushButton('Red pixel', self)
            self.extract_r_btn.setGeometry(20, cnt_h, btn_w, btn_h)
            self.extract_r_btn.setStyleSheet('background-color: red; color: white')
            self.extract_r_btn.clicked.connect(lambda: self.extract_pixel(self.count_r_window))
            self.extract_r_btn.setShortcut('Alt+r')

            self.extract_b_btn = Qw.QPushButton('Blue pixel', self)
            self.extract_b_btn.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)
            self.extract_b_btn.setStyleSheet('background-color: blue; color: white')
            self.extract_b_btn.clicked.connect(lambda: self.extract_pixel(self.count_b_window))
            self.extract_b_btn.setShortcut('Alt+b')
            cnt_h += 32

            self.count_r_label = Qw.QLabel('Count: ', self)
            self.count_r_label.setGeometry(20, cnt_h, btn_w, btn_h)

            self.count_r_window = Qw.QLineEdit(self)
            self.count_r_window.setGeometry(20 + count_w, cnt_h, window_w, btn_h)
            self.count_r_window.setReadOnly(True)

            self.count_b_label = Qw.QLabel('Count: ', self)
            self.count_b_label.setGeometry(20 + btn_w + 5, cnt_h, btn_w, btn_h)

            self.count_b_window = Qw.QLineEdit(self)
            self.count_b_window.setGeometry(20 + btn_w + 5 + count_w, cnt_h, window_w, btn_h)
            self.count_b_window.setReadOnly(True)
            cnt_h += 40

        self.set_default = Qw.QPushButton('Initialize', self)
        self.set_default.setGeometry(20, cnt_h, btn_w, btn_h)
        self.set_default.clicked.connect(self.default_image)
        self.set_default.setShortcut('Alt+d')

        self.statusBar().showMessage('Ready')

    def load_image(self):
        # print('Load DICOM image')
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

        elif index_type == 'slice':
            self.dcm_slice = self.image_array[self.slice_index - 1]

        else:
            raise ValueError('Error! Invalid index type.')

        if self.first_load:
            self.ax.imshow(self.dcm_slice)
            self.canvas.draw()

            self.canvas.callbacks.connect('motion_notify_event', self.motion_coord)
            self.canvas.callbacks.connect('button_press_event', self.rect_press)
            self.canvas.callbacks.connect('motion_notify_event', self.rect_draw)
            self.canvas.callbacks.connect('button_release_event', self.rect_release)
            self.canvas.callbacks.connect('button_press_event', self.rect_remove)

            self.first_load = False
        else:
            self.ax.clear()
            self.ax.imshow(self.dcm_slice)

            if self.end_x is not None and self.end_y is not None:
                self.rect_load()

            self.canvas.draw()

        self.file_label.setText('%d/%d' % (self.file_index, self.file_num))
        self.slice_label.setText('%d/%d' % (self.slice_index, self.slice_num))

        self.count_window.setText('')
        # self.count_r_window.setText('')
        # self.count_b_window.setText('')

        self.statusBar().showMessage('Image upload')

    def rect_load(self):
        for idx in range(1, self.rect_num + 1):
            rect_w = abs(self.end_x[idx] - self.start_x[idx])
            rect_h = abs(self.end_y[idx] - self.start_y[idx])
            self.rect_set[idx] = patches.Rectangle(xy=(self.start_x[idx], self.start_y[idx]),
                                                   width=rect_w, height=rect_h, fill=False, color='gold')

            self.ax.add_patch(self.rect_set[idx])

    def default_rect(self):
        for idx in range(1, self.rect_num + 1):
            self.start_x.pop(idx)
            self.start_y.pop(idx)
            self.end_x.pop(idx)
            self.end_y.pop(idx)
            self.ext_set.pop(idx)
            self.rect_set.pop(idx)

    def default_image(self):
        if self.first_load is False:
            if self.rect_num > 0:
                self.default_rect()

                self.ax.clear()
                self.ax.imshow(self.dcm_slice)
                self.canvas.draw()

                self.rect_num = 0
                self.statusBar().showMessage('Default image')
            else:
                self.popup_box('Error!', 'No region was marked.')
        else:
            self.popup_box('Error!', 'Please upload image.')

    def motion_coord(self, event):
        if event.inaxes is not None:
            if int(event.xdata) < self.dcm_slice.shape[1] and int(event.ydata) < self.dcm_slice.shape[0]:
                m_r, m_g, m_b = self.dcm_slice[int(event.ydata), int(event.xdata), ]
                motion_text = 'X: %d, Y: %d' % (int(event.xdata), int(event.ydata))

                value_text = 'Val: %d, %d, %d' % (m_r, m_g, m_b)
                total_text = motion_text + '  ' + value_text
                self.coord_label.setText(total_text)
            else:
                return
        else:
            return

    def rect_press(self, event):
        if event.inaxes is not None and event.button == 1:
            self.start_x[self.rect_num + 1], self.start_y[self.rect_num + 1] = int(event.xdata), int(event.ydata)
            self.rect_set[self.rect_num + 1] = patches.Rectangle(xy=(self.start_x[self.rect_num + 1],
                                                                     self.start_y[self.rect_num + 1]),
                                                                 width=1, height=1, fill=False, color='gold')
            self.ax.add_patch(self.rect_set[self.rect_num + 1])
            self.canvas.draw()
        else:
            return

    def rect_draw(self, event):
        if event.inaxes is not None and event.button == 1:
            self.rect_set[self.rect_num + 1].set_height(int(event.ydata) - self.start_y[self.rect_num + 1])
            self.rect_set[self.rect_num + 1].set_width(int(event.xdata) - self.start_x[self.rect_num + 1])
            self.canvas.draw()
        else:
            return

    def rect_release(self, event):
        if event.inaxes is not None and event.button == 1:
            self.end_x[self.rect_num + 1], self.end_y[self.rect_num + 1] = int(event.xdata), int(event.ydata)

            cnt_x1, cnt_x2 = self.start_x[self.rect_num + 1], self.end_x[self.rect_num + 1]
            cnt_y1, cnt_y2 = self.start_y[self.rect_num + 1], self.end_y[self.rect_num + 1]

            region_lt = 'X: %d, Y: %d' % (min(cnt_x1, cnt_x2), min(cnt_y1, cnt_y2))
            region_rb = 'X: %d, Y: %d' % (max(cnt_x1, cnt_x2), max(cnt_y1, cnt_y2))

            region_w = str(abs(cnt_y1 - cnt_y2))
            region_h = str(abs(cnt_x1 - cnt_x2))

            self.region_lt_value.setText(region_lt)
            self.region_rb_value.setText(region_rb)
            self.region_w_value.setText(region_w)
            self.region_h_value.setText(region_h)

            self.ext_set[self.rect_num + 1] = False
            self.rect_num += 1
            # print(self.rect_set, self.rect_num)
        else:
            return

    def rect_remove(self, event):
        if event.inaxes is not None and event.button == 2:
            if self.rect_num > 0:
                self.rect_set[self.rect_num].remove()
                self.canvas.draw()
                self.start_x.pop(self.rect_num)
                self.start_y.pop(self.rect_num)
                self.end_x.pop(self.rect_num)
                self.end_y.pop(self.rect_num)
                self.rect_num -= 1

                # print(self.rect_set, self.rect_num)
            else:
                self.popup_box('Error!', 'There is no region to remove.')

    def extract_pixel(self, result_window):
        if self.first_load is False:
            # if self.is_rect:
            if self.rect_num > 0:
                # if True:
                is_r = len(self.value_r.text()) > 0
                is_g = len(self.value_g.text()) > 0
                is_b = len(self.value_b.text()) > 0

                if is_r and is_g and is_b:
                    valid_r = re.search('\D', self.value_r.text())
                    valid_g = re.search('\D', self.value_g.text())
                    valid_b = re.search('\D', self.value_b.text())

                    if valid_r is None and valid_g is None and valid_b is None:
                        def threshold_process(line_edit):
                            threshold = line_edit.text()
                            threshold = int(threshold)
                            if threshold < 0:
                                threshold = 0
                            elif threshold > 255:
                                threshold = 255
                            line_edit.setText(str(threshold))
                            return threshold

                        threshold_r = threshold_process(self.value_r)
                        threshold_g = threshold_process(self.value_g)
                        threshold_b = threshold_process(self.value_b)

                        zeros_image = np.zeros(self.dcm_slice.shape, dtype=self.dcm_slice.dtype)

                        x1 = min(self.start_x[self.rect_num], self.end_x[self.rect_num])
                        x2 = max(self.start_x[self.rect_num], self.end_x[self.rect_num])
                        y1 = min(self.start_y[self.rect_num], self.end_y[self.rect_num])
                        y2 = max(self.start_y[self.rect_num], self.end_y[self.rect_num])

                        self.adjust_image = self.dcm_slice - zeros_image

                        if abs(x1 - x2) >= 2 and abs(y1 - y2) >= 2:
                            pixel_result = np.apply_along_axis(lambda x:
                                                               extract_rgb_all(x,
                                                                               self.radio_r_more.isChecked(),
                                                                               self.radio_g_more.isChecked(),
                                                                               self.radio_b_more.isChecked(),
                                                                               threshold_r,
                                                                               threshold_g,
                                                                               threshold_b),
                                                               2, self.adjust_image[y1:y2, x1:x2])

                            self.adjust_image[y1:y2, x1:x2] = pixel_result

                            pixel_count = np.sum(np.apply_along_axis(count_value, 2, pixel_result))
                            result_window.setText(str(pixel_count))

                            self.ax.clear()
                            self.ax.imshow(self.adjust_image)
                            self.rect_load()
                            self.canvas.draw()

                            self.ext_set[self.rect_num] = True

                            self.statusBar().showMessage('Done')
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
                       'Image viewer for Doppler ultrasonography v0.9\nDeveloped by Dongjun Choi')

    def popup_box(self, popup_title, popup_message):
        Qw.QMessageBox.about(self, popup_title, popup_message)

    def run_app(self):
        self.setGeometry(200, 40, widget_width + 70, widget_height + 10)
        self.setWindowTitle('US viewer v0.9')
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
