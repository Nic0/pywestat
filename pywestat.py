#!/usr/bin/python2.7
# -*- coding: utf-8 -*-

# Copyright (c) 2011, Nicolas Paris <nicolas.caen@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the <organization> nor the
#      names of its contributors may be used to endorse or promote products
#      derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL NICOLAS PARIS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import time
import sched
import urwid
import pickle
import inspect
import logging
import pymetar
import datetime
import threading
from urllib2 import URLError

def current_line():
    return inspect.currentframe().f_back.f_lineno

class DataHandler(object):
    """serialize datas with pickler"""

    def __init__(self):
        self.datafile = 'weather.db'
        self.load()

    def load(self):
        try:
            with open(self.datafile, 'rb') as f:
                self.data = pickle.load(f)
        except (EOFError, IOError):
            self.data = []

    def save(self):
        with open(self.datafile, 'wb') as f:
            pickle.dump(self.data, f)

    def append(self, data):
        if len(self.data) > 0 and data not in self.data:
            if self.data[-1].time != data.time:
                self.data.append(data)
        else:
            self.data.append(data)
        

class WeatherData(object):
    """Simple object C-structure like
       used to store data from one report"""
    
    def __init__(self, time, temp, press):
        self.time = time
        self.temp = temp
        self.press = press

    def __repr__(self):
        return repr((self.time, self.temp, self.press))

class UpdateThread(threading.Thread):
    """Thread updating the repport datas"""

    def __init__(self, weather):
        self.sched = sched.scheduler(time.time, time.sleep)
        self.weather = weather
        super(UpdateThread, self).__init__()

    def run(self):
        while True:
            time.sleep(1)
            if self.sched.empty():
                logging.debug('scheduler update')
                self.scheduler()

    def scheduler(self):
        self.event = self.sched.enter(60, 1, self.weather.update_report, ())
        try:
            self.sched.run()
        except (TypeError, URLError), e:
            logging.warning('%s (l.%s)' % (e, current_line()))
        except Exception, e:
            logging.warning('%s line %s' % (e, current_line()))
            

class RefreshThread(threading.Thread):
    """Refresh the time clock in the bottom"""

    def __init__(self, weather):
        self._stop = False
        self.weather = weather
        threading.Thread.__init__(self, target=self.run)
        self._stopevent = threading.Event()

    def run(self):
        time.sleep(1)
        while self._stop == False:
            self.weather.update_time()
            time.sleep(1)
            
    def stop(self):
        self._stop = True

class WeatherWidget(urwid.WidgetWrap):
    """Widget wrapping a two columns for data display"""
    
    def __init__(self, id, title, value):
        self.id = id
        self.title = title
        self.value = urwid.Text(value)
        self.widget = [        
                ('fixed', 20, urwid.Padding(urwid.AttrWrap(urwid.Text(self.title),
                    'body'), left=2)),
                urwid.AttrWrap(self.value, 'data')
                ]
        w = urwid.Columns(self.widget)
        self.__super.__init__(w)

    def keypress(self, size, key):
        return key

class Header(urwid.WidgetWrap):
    """Build the header with station name and date report"""

    def __init__(self, header):
        self.header = urwid.Text(header)
        w = urwid.Pile([
            urwid.Divider(' '),
            urwid.Padding(urwid.AttrWrap(self.header, 'header'), left=5),
            urwid.Divider(' '),
            ])
        self.__super.__init__(w)

    def keypress(self, size, key):
        return key

class Interface(object):
    """Main entry point for the interface display and for the entire program"""

    def __init__(self):
        self.station = 'LFRK'
        self.item = []
        self.report = self.retrieve_report()
        self.init_prog()

    def init_prog(self):
        self.datahandler = DataHandler()
        self.init_logging()
        self.init_unit()
        self.init_palette()
        self.display_report()
        self.init_loop_and_threads()

    def init_logging(self):
        logging.basicConfig(
            filename='weather.log',
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)s - %(message)s',
            datefmt='%d/%m/%Y %H:%M:%S',
            )

    def init_unit(self):
        self.unit = {
                'temp': '°C',
                'dew': '°C',
                'wind_chill': '°C',
                'press': 'hPa',
                'hum': '%',
                'wind_speed': 'km/h',
                'vis': 'km',
                }

    def init_loop_and_threads(self):
        update = UpdateThread(self)
        refresh = RefreshThread(self)
        update.start()
        refresh.start()
        self.loop = urwid.MainLoop(self.display, self.palette, unhandled_input=self.keystroke)
        logging.info('Starting Weather')
        self.loop.run()
        refresh.stop()
        update._Thread__stop()

    def retrieve_report(self):
        rf=pymetar.ReportFetcher(self.station)
        rep=rf.FetchReport()
        rp=pymetar.ReportParser()
        return rp.ParseReport(rep)

    def display_report(self):
        self.data = self.get_data()
        data = self.data
        self.persiste_data(data)
        self.template = [
                ['temp', 'Temperature:', data['temp']],
                ['dew', 'Dew Point:', data['dew']],
                ['wind_chill', 'Wind Chill:', data['wind_chill']],
                ['press', 'Pressure:', data['press']],
                ['hum', 'Humidity:', data['hum']],
                ['wind_dir', 'Wind Direction:', data['wind_dir']],
                ['wind_speed', 'Wind Speed:', data['wind_speed']],
                ['vis', 'Visibility:', data['vis']],
                ['sky_cond', 'Sky Condition:', data['sky_cond']],
                ['weather', 'Weather:', data['weather']],
                 ]

        for key, value in enumerate(self.template):
            try:
                self.template[key][2] = value[2] +' '+ self.unit[value[0]]
            except KeyError:
                pass

        self.add_header()
        self.add_diviser('Datas', 10)
        for i in self.template[:5]:
            self.item.append(WeatherWidget(i[0], i[1], i[2]))
        self.add_diviser('Weather', 10)
        for i in self.template[5:]:
            self.item.append(WeatherWidget(i[0], i[1], i[2]))
        self.add_diviser(str(self.get_time()), 5)

        self.display = urwid.ListBox(self.item)

    def persiste_data(self, data):
        self.datahandler.append(WeatherData(data['time'], data['temp'], data['press']))
        self.datahandler.save()

    def get_data(self):
        rp = self.report

        try:
            temp =  '%d' % rp.getTemperatureCelsius()
        except TypeError:
            temp = 'None'
        try:
            dew = '%d' % rp.getDewPointCelsius()
        except TypeError:
            dew = 'None'
        try:
            wind_chill = '%.1f' % rp.getWindchill()
        except TypeError:
            wind_chill = 'None'
        try:
            press = '%d' % rp.getPressure()
        except TypeError:
            press = 'None'
        try:
            hum = '%d' % rp.getHumidity()
        except TypeError:
            hum = 'None'
        try:
            wind_speed = '%d' % (rp.getWindSpeed()*3622/1000)
        except TypeError:
            wind_speed = 'None'
        try:
            vis = '%.1f' % rp.getVisibilityKilometers()
        except TypeError:
            vis = 'None'

        return {
                'temp': temp,
                'dew': dew,
                'wind_chill': wind_chill,
                'press': press,
                'hum': hum,
                'wind_dir': '%s° (%s)' % (rp.getWindDirection(), rp.getWindCompass()),
                'wind_speed': wind_speed,
                'vis': vis,
                'sky_cond': '%s' % rp.getSkyConditions(),
                'weather': '%s' % rp.getWeather(),
                'time': rp.getISOTime(),
            }

    def get_time(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def update_time(self):
        t = self.get_time()
        self.item[-2] = (urwid.Padding(urwid.AttrWrap(urwid.Text(t),
        'header'), left=5))
        self.loop.draw_screen()
        self.check_update_alive()

    def check_update_alive(self):
        if threading.active_count() == 1:
            self.restart_update()

    def restart_update(self):
        logging.debug('restarting an update thread')
        update = UpdateThread(self)
        update.start()

    def update_report(self):
        logging.debug('trying update')
        new_report = self.retrieve_report()
        if self.report.getTime() != new_report.getTime():
            logging.debug('start update')
            old_data = self.get_data()
            self.report = new_report
            new_data = self.get_data()
            self.persiste_data(new_data)

            for key, val in enumerate(self.item):
                if hasattr(val, 'id') and val.id in ['temp', 'dew', 'wind_chill', 'press', 'hum',
                        'wind_speed', 'vis']:
                    try:
                        if new_data[val.id] != 'None' or old_data[val.id] != 'None':
                            diff = float(new_data[val.id]) - float(old_data[val.id])
                        else:
                            diff = 0.0
                    except TypeError:
                        diff = 0.0

                    pos_icon = u"\u25B2".encode('utf-8')
                    neg_icon = u"\u25BC".encode('utf-8')

                    try:
                        if diff > 0:
                            diff = ('pos', ' %.1f %s' % (diff, pos_icon))
                        elif diff < 0:
                            diff = ('neg', ' %.1f %s' % (diff, neg_icon))
                        else:
                            diff = ('equal', ' =')
                    except:
                        diff = ''
                        logging.warning('error with diff')
                    unit = ' %s' % self.unit[val.id]
                    try:
                        val.value.set_text(['%s %s' % (new_data[val.id], unit), diff])
                    except:
                        logging.warning('line %s' % current_line())

                
                logging.debug('update -- %s (%s)' % (self.format_header(), self.get_time()))
                self.update_header()
                self.loop.draw_screen()
                logging.debug('stop update')

    def add_diviser(self, title, pad):
        self.item.append(urwid.Divider(' '))
        self.item.append(urwid.Padding(urwid.AttrWrap(urwid.Text(title),
        'header'), left=pad))
        self.item.append(urwid.Divider(' '))

    def keystroke(self, ch):
        if ch == 'q':
            raise urwid.ExitMainLoop()

    def update_header(self):
        try:
            self.item[0].header.set_text(self.format_header())
        except:
            logging.warning('line %s' % current_line())

    def add_header(self):
        self.item.append(Header(self.format_header()))

    def format_header(self):
        try:
            rp = self.report
            header = '{name} ({t_report})'.format(
                    name=rp.getStationName(),
                    t_report=rp.getISOTime().split(' ')[1][:-4],
                    )
        except:
            logging.warning('line %s' % current_line())
        return header

    def init_palette(self):
        self.palette = [
            ('body','dark cyan', '', ''),
            ('header','dark red', '', ''),
            ('data','brown', '', ''),
            ('neg','dark red', ''),
            ('pos','dark green', ''),
            ('equal', 'light blue', ''),
            ]

if __name__ == '__main__':
    Interface()

