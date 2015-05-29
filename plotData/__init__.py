#!/usr/bin/env python

import sys

import argparse
from collections import deque
import threading
from Queue import Queue
import time

import serial
import numpy as np
from pyqtgraph.Qt import QtGui
from pyqtgraph.Qt import QtCore
import pyqtgraph as pg

TIME_STEP = 2. # Time in seconds between plot updates for function mode and
               # IV_curve.  This is needed because scatter plots are slow in
               # pyqtgraph :(

def timefunc(f):
    """ Used for timing function calls

        To use, simply place "@timefunc" above the function you wish to time
    """
    def f_timer(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        print f.__name__, 'took', end - start, 'time'
        return result
    return f_timer

class AnalogData(object):
    """ Class that holds data for N (args.maxLen) samples
    """
    def __init__(self, args):
        """ Build deques
        """
        self.port = args.port
        self.baudrate = args.baudrate
        self.ADC_resolution = args.ADC_resolution
        self.maxLen = args.maxLen
        self.msec = args.msec
        self.Vref = args.Vref
        self.display_voltage = args.display_voltage
        self.function_mode = args.function_mode
        self.IV_curve = args.IV_curve
        self.series_resistance = args.series_resistance
        self.logx = args.logx
        self.logy = args.logy
        self.DFT = not args.noDFT
        self.noPrint = args.noPrint
        self.columns = [args.c0, args.c1, args.c2, args.c3, args.c4, args.c5, 
                        args.c6, args.c7]
        self.num_columns = self.columns.count(True)
        
        deques = dict()
        for i, val in enumerate(self.columns):
            if val:
                deque_name = 'c%d' % i
                deques[deque_name] = deque([0.0] * self.maxLen)
                if self.DFT:
                    fft_name = 'c%d_fft' % i
                    deques[fft_name] = deque([0.0] * self.maxLen)
                    
        deques['mission_time'] = deque([0.0] * self.maxLen)
        if self.DFT:
            deques['frequency'] = deque([0.0] * self.maxLen)
            
        self.deques = deques
        
    def add_data(self, data):
        self.addToBuf(self.deques['mission_time'], data[0])
        for i, val in enumerate(self.columns):
            if val:
                self.addToBuf(self.deques['c%d' % i], data[i])
                
    def addToBuf(self, buf, val):
        """ Ring buffer
        """
        if len(buf) < self.maxLen:
            buf.append(val)
        else:
            buf.pop()
            buf.appendleft(val)
                    
class AnalogPlot(object):
    """ Plot class
    """
    def __init__(self, analogData):
        self.analogData = analogData
        self.sample_indicies = np.arange(analogData.maxLen)
        self.maxVal = 2**analogData.ADC_resolution - 1
        
        self.app = QtGui.QApplication([])
        self.win = pg.GraphicsWindow(title='Serial data')
        
        # Enable antialiasing for prettier plots, disable for increased
        # performance
        #pg.setConfigOptions(antialias=True)
        
        self.p1 = self.win.addPlot()
        if analogData.display_voltage:
            self.p1.setYRange(0, analogData.Vref)
            self.p1.setLabel('left', 'Voltage (V)')
        else:
            self.p1.setYRange(0, self.maxVal)
            self.p1.setLabel('left', 'Voltage')
        self.p1.enableAutoRange('y', False)
        self.p1.showGrid(x=True, y=True)
        self.p1.setLabel('bottom', 'Time (s)')
        
        self.curves1 = list()
        self.colors = ['b', 'g', 'r', 'c', 'm', 'y', 'w']
        for i, val in enumerate(analogData.columns):
            if val:
                curve = self.p1.plot(pen=self.colors[i])
                self.curves1.append(curve)
        
        if analogData.DFT:
            self.setup_DFT()
      
        if analogData.function_mode:
            self.setup_function_mode()
            
        if analogData.IV_curve:
            self.setup_IV_curve()
            
        self.numlines = 0
            
    def setup_DFT(self):
        """ View amplitude spectrum
        """
        self.win.nextRow()
        self.p2 = self.win.addPlot()
        self.p2.showGrid(x=True, y=True)
        
        # Plot frequency and / or amplitude on log scale
        if self.analogData.logx and self.analogData.logy:
            self.p2.setLogMode(x=True, y=True)
        elif self.analogData.logx:
            self.p2.setLogMode(x=True, y=False)
        elif self.analogData.logy:
            self.p2.setLogMode(x=False, y=True)
        
        self.p2.setLabel('bottom', 'Frequency (Hz)')
        if self.analogData.display_voltage:
            self.p2.setLabel('left', 'Amplitude spectrum (V)')
        else:
            self.p2.setLabel('left', 'Amplitude spectrum')
        
        self.curves2 = list()
        for i, val in enumerate(self.analogData.columns):
            if val:
                curve = self.p2.plot(pen=self.colors[i])
                self.curves2.append(curve)
                    
    def setup_function_mode(self):
        """ f(c1) = c2
        
            When function mode is enabled, c2 will be plotted against c1 in a
            separate window.
        """
        self.time_update_func = 0.
        self.win_func = pg.GraphicsWindow(title='c2 vs. c1')
        self.p3 = self.win_func.addPlot()
        if self.analogData.display_voltage:
            self.p3.setXRange(0, self.analogData.Vref)
            self.p3.setYRange(0, self.analogData.Vref)
            self.p3.setLabel('bottom', 'Input voltage c1 (V)')
            self.p3.setLabel('left', 'Output voltage c2 (V)')
        else:
            self.p3.setXRange(0, self.maxVal)
            self.p3.setYRange(0, self.maxVal)
            self.p3.setLabel('bottom', 'Input c1')
            self.p3.setLabel('left', 'Output c2')
        self.p3.enableAutoRange('x', False)
        self.p3.enableAutoRange('y', False)
        self.p3.showGrid(x=True, y=True)
        self.func_curve = self.p3.plot(pen=None, #symbol='x',
                                       symbolPen='y', symbolBrush='y')
                                                                              
    def setup_IV_curve(self):
        """ Plots I-V characteristics of circuit component.
        
            With this option, it is necessary for c1 to be voltage at the
            positive terminal of circuit component and for c2 to be voltage at
            the negative terminal of circuit component, with circuit component
            in series with a pull up resistor of resistance [SERIES_RESISTANCE]
            ohms.
        """
        self.time_update_IV = 0.
        self.win_IV = pg.GraphicsWindow(title='I-V curve')
        self.p4 = self.win_IV.addPlot()
        self.p4.setXRange(0, self.analogData.Vref)
        self.p4.setLabel('bottom', 'Voltage (V)')
        self.p4.setLabel('left', 'Current (mA)')
        self.p4.enableAutoRange('x', False)
        self.p4.showGrid(x=True, y=True)
        self.IV_curve = self.p4.plot(pen=None, #symbol='x',
                                     symbolPen='y', symbolBrush='y')
    
    def fft(self):
        for i, val in enumerate(self.analogData.columns):
            if val:
                a = np.array(self.analogData.deques['c%d' % i])[self.sample_indicies]
                self.analogData.deques['c%d_fft' % i] = np.absolute(np.fft.rfft(a))

        # gives the spectrum in Hertz
        frequency = np.fft.rfftfreq(np.size(a), d = 1. / self.sample_rate)
        self.analogData.deques['frequency'] = frequency
    
    def plot(self):
        curve_count = 0
        full_t_array = (np.array(self.analogData.deques['mission_time']) /
                        1000000.)
        t_array = full_t_array[self.sample_indicies]
        for i, val in enumerate(self.analogData.columns):
            if val:
                curve = np.array(self.analogData.deques['c%d' % i])[self.sample_indicies]
                if self.analogData.display_voltage:
                    curve = (self.analogData.Vref * curve) / self.maxVal
                
                # Draw time domain plot
                self.curves1[curve_count].setData(t_array, curve)
                
                if self.analogData.DFT and self.numlines >= self.analogData.maxLen:
                    fft_curve = np.array(self.analogData.deques['c%d_fft' % i])
                    if self.analogData.display_voltage:
                        fft_curve = (self.analogData.Vref *
                                     fft_curve) / self.maxVal
                    
                    # Draw frequency domain plot
                    self.curves2[curve_count].setData(self.analogData.deques['frequency'],
                                  fft_curve)
                                  
                curve_count += 1
                
            if self.analogData.function_mode and self.analogData.display_voltage:
                if i==1:
                    func_domain = curve
                if i==2:
                    func_val = curve
                    time_elapsed = time.time()
                    if time_elapsed > self.time_update_func:
                        self.func_curve.setData(func_domain, func_val)
                        self.time_update_func = time_elapsed + TIME_STEP
    
        if self.analogData.function_mode and not self.analogData.display_voltage:
            time_elapsed = time.time()
            if time_elapsed > self.time_update_func:
                self.func_curve.setData(self.analogData.deques['c1'],
                                        self.analogData.deques['c2'])
                self.time_update_func = time_elapsed + TIME_STEP
                
        if self.analogData.IV_curve:
            time_elapsed = time.time()
            if time_elapsed > self.time_update_IV:
                self.plot_IV_curve()
                self.time_update_IV = time_elapsed + TIME_STEP
    
    def plot_IV_curve(self):
        Vin = (self.analogData.Vref *
               np.array(self.analogData.deques['c1'])) / self.maxVal
        Vout = (self.analogData.Vref *
                np.array(self.analogData.deques['c2'])) / self.maxVal

        V_load = Vin - Vout
        current = Vout / self.analogData.series_resistance
        current_mA = current * 1000. # convert from A to mA

        self.IV_curve.setData(V_load, current_mA)
    
    def sample_rate_stats(self, t_array):
        """ Calculate differences in t_array with mean, standard deviation, min
            sample rate, and relative standard deviation.
            
            Returns sample_rate, relative_std, min_diff
        """
        diffs = np.diff(t_array[::-1])
        mean_diffs = np.mean(diffs)
        std_diffs = np.std(diffs)
        min_diff = np.min(diffs)
        
        sample_rate = 1. / mean_diffs # Hz
        relative_std = std_diffs / mean_diffs
        
        return(sample_rate, relative_std, min_diff)
    
    def subsample_data(self):
        t_array = np.array(self.analogData.deques['mission_time']) / 1000000.
        subsample_indicies = np.arange(t_array.size)
        sample_rate, relative_std, min_diff = self.sample_rate_stats(t_array)
        
        if relative_std > 0.01:
            irregular = True
            initial_sample_rate = sample_rate
        else:
            irregular = False
            
        while relative_std > 0.01 or min_diff==0:
            # relative standard deviation is greater than 1%, decrease sample 
            # rate
            subsample_rate = sample_rate / 2.
            t_step = 1. / subsample_rate
            target_t_array = np.arange(t_array[0],t_array[-1], -t_step)
            
            subsample_indicies = np.empty(np.size(target_t_array))
            for i, target_t in enumerate(target_t_array):
                subsample_indicies[i] = np.argmin(np.abs(target_t - t_array))
                
            subsample_t_array = t_array[subsample_indicies.astype(int)]
                
            sample_rate, relative_std, min_diff = self.sample_rate_stats(subsample_t_array)
            
        self.sample_rate = sample_rate
        self.sample_indicies = subsample_indicies.astype(int)
        if irregular:
            sys.stderr.write('Sample rate at %r Hz is irregular.  Subsampling '
                             'data at %r Hz...\n' % (initial_sample_rate, 
                                                     sample_rate))
                                                 
    def run_event_loop(self):
        # Open serial port
        self.ser = serial.Serial(self.analogData.port, self.analogData.baudrate)
        
        # Open queue, start input thread
        self.serial_queue = Queue()
        self.serial_thread = threading.Thread(target=self.read_serial)
        self.serial_thread.start()
        
        timer = QtCore.QTimer()
        timer.timeout.connect(self.update)
        timer.start(self.analogData.msec)
        QtGui.QApplication.instance().exec_()
        
    def update(self):
        while self.serial_queue.empty() == False:
            line = self.serial_queue.get()
            try:
                data = [float(val) for val in line.split()]
                if not self.analogData.noPrint:
                    print('%s' % line.rstrip())
                self.analogData.add_data(data)
                if self.numlines <= self.analogData.maxLen:
                    self.numlines += 1
            except ValueError:
                sys.stderr.write('WARNING:  Read unexpected value in %r' % line)
        if self.numlines >= self.analogData.maxLen and self.analogData.DFT:
            self.subsample_data()
            self.fft()
        self.plot()
        
    def read_serial(self):
        try:
            while True:
                line = self.ser.readline()
                self.serial_queue.put(line)
        except KeyboardInterrupt:
            print('exiting')
            # Close serial
            self.ser.close()

def get_args():
    parser = argparse.ArgumentParser(description='Plot serial data received '
                                     'via the USB port.  Designed for use with '
                                     'Arduino microcontrollers.  --cx flags '
                                     'correspond to which column of serial '
                                     'data to plot (if none are selected will '
                                     'default to --c1).  NOTE - the first '
                                     'column of data (c0) MUST be the time in '
                                     'microseconds at which data were '
                                     'collected.')
    parser.add_argument('-p', '--port', type=str, help='Device name or port '
                        'number.')
    parser.add_argument('-b', '--baudrate', type=int, default=9600,
                        help='Baud rate such as 9600 or 115200 etc.')
    parser.add_argument('-r', '--ADC_resolution', type=int, default=10)
    parser.add_argument('-L', '--maxLen', type=int, default=1000)
    parser.add_argument('-m', '--msec', type=int, default=16, help='Time in '
                        'ms between plot updates.')
    parser.add_argument('-v', '--display_voltage', action='store_true')
    parser.add_argument('-V', '--Vref', type=float, default=5.)
    parser.add_argument('-f', '--function_mode', action='store_true',
                        help='Display f(c1) = c2.  When function_mode is '
                        'enabled, c2 will be plotted against c1 in a separate '
                        'window.  NOTE - enabling function_mode will also '
                        'enable --c1 and --c2.')
    parser.add_argument('-I', '--IV_curve', action='store_true',
                        help='Plots I-V characteristics of circuit component.  '
                        'With this option, it is necessary for c1 to be '
                        'voltage at the positive terminal of circuit '
                        'component and for c2 to be voltage at the negative '
                        'terminal of circuit component, with circuit component '
                        'in series with a pull up resistor of resistance '
                        '[SERIES_RESISTANCE] ohms.  NOTE - enabling IV_curve '
                        'will also enable --c1, --c2, and --display_voltage.')
    parser.add_argument('-R', '--series_resistance', type=float, default=220.,
                        help='Resistance in ohms of series resistor to '
                        'measure current through.')
    parser.add_argument('--logx', action='store_true', help='Plot frequency '
                        'on log scale.')
    parser.add_argument('--logy', action='store_true', help='Plot amplitude '
                        'on log scale.')
    parser.add_argument('--noDFT', action='store_true')
    parser.add_argument('--noPrint', action='store_true')
    #parser.add_argument('--c0', action='store_true')
    parser.add_argument('--c1', action='store_true')
    parser.add_argument('--c2', action='store_true')
    parser.add_argument('--c3', action='store_true')
    parser.add_argument('--c4', action='store_true')
    parser.add_argument('--c5', action='store_true')
    parser.add_argument('--c6', action='store_true')
    parser.add_argument('--c7', action='store_true')
    
    args = parser.parse_args()
        
    if args.function_mode:
        args.c1 = True
        args.c2 = True
        
    if args.IV_curve:
        args.c1 = True
        args.c2 = True
        args.display_voltage = True
    
    # Plot c1 if no --cx flags toggled    
    no_columns = True
    columns = [args.c1, args.c2, args.c3, args.c4, args.c5, args.c6, args.c7]
    for i, column in enumerate(columns):
        if column:
            no_columns = False
    if no_columns:
        args.c1 = True
    
    args.c0 = False # We do not wish to plot time on vertical axis
    
    return args

def run():
    args = get_args()
    analogData = AnalogData(args)
    analogPlot = AnalogPlot(analogData)
    analogPlot.run_event_loop()
        
def main():
    run()

if __name__=='__main__':
    main()