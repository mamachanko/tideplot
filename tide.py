# -*- coding=utf-8 -*-
# /usr/bin/python

from BeautifulSoup import BeautifulSoup as soup
import httplib2
import sys
import datetime
import urllib2
from optparse import OptionParser
import re
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TIDE_URL = 'http://www.gezeiten-kalender.de'

def calenderReachable():
    try:
        response = urllib2.urlopen(TIDE_URL, timeout=1)
        return True
    except urllib2.URLError as err: pass
    return False

def listLocations(verbose=False):
    conn = httplib2.Http(".cache")
    url = TIDE_URL + ':9099/zones/:Europe/Berlin'
    if verbose:
        print 'retrieving...(%s)\n' % url
    page = conn.request(url, 'GET')
    html = soup(page[1])
    
    locregx = re.compile('/locations/[0-9]+.html')
    locations = html.findAll('a', attrs={'href': locregx})
    maxname = max(map(lambda x: len(x.string), locations))
    locdict = {} 
    keydict = {}
    for loc in locations:
        locname = loc.string
        lockey = loc.get('href').rstrip('.html').lstrip('/locations/')
        locdict[locname] = int(lockey)
        keydict[int(lockey)] = locname
        if verbose:
            print '%s %s' % (locname.ljust(maxname+2), lockey)
    return locdict, keydict

def getTide(date=datetime.datetime.now(), location=1208, verbose=False):
    urlbase = TIDE_URL + ':9099/locations/%s.html' % location
    urldate = '?y=%s&m=%s&d=%s' % (date.year, date.month, date.day)
    url = urlbase + urldate
    
    conn = httplib2.Http(".cache")
    if verbose:
        print 'retrieving...(%s)\n' % url
    page = conn.request(url, 'GET')
    html = soup(page[1])
    pres = html.findAll('pre')
    data = pres[0].string
    data = [x for x in data.split('\n') if len(x)>0]
    
    day = str(date.day).zfill(2)
    month = str(date.month).zfill(2)
    year = date.year
    
    locname = data[0]
    coords = data[1]
    tide = [x for x in data[2:] if x.endswith('wasser')]
    tide = [x for x in tide if x.startswith('%s.%s.%s' % (day, month, year))]
    
    if verbose:
        print 'Location:'
        print '    %s (%s)' % (locname, coords)
        print 'Tide details:'
    levels = []
    for s in tide:
        l = s.split('   ')
        date = datetime.datetime.strptime(l[0], '%d.%m.%Y %H:%M %Z')
        r = l[1].split('  ')
        level = abs(round(float(r[0].rstrip(' Meter')), 2))
        high = 1
        if r[1] == 'Niedrigwasser':
            high = 0
        levels.append((date, level, high))
        if verbose:
            print '   ', date, level, 'm', high
    return levels

def optParser():
    parser = OptionParser()
    parser.add_option("-d", "--date",
                      dest="date",
                      help="the date for which to look up in the tide table given in 'DD-MM-YYYY' or 'DD-MM-YYYY hh:mm' format. if not given today will be assumed.",
                      default=datetime.datetime.today().strftime('%d-%m-%Y-%H:%M'),
                      metavar="DATE")
    parser.add_option("-l", "--location",
                      dest="location",
                      default="1208",
                      help="the key defining the location for which to look up at the tide table. for a listing of all locations and their keys see the '--list-locations' option.",
                      metavar="LOCATION")
    parser.add_option("-a", "--list-locations",
                      dest="list_locations",
                      action="store_true",
                      default=False,
                      help="lists all available locations and their respective key.")
    
    parser.add_option("-p", "--plot-levels",
                      dest="plot",
                      action="store_true",
                      default=False,
                      help="plot levels with pylab.")

    return parser

def level(date=datetime.datetime.now(), location=1208, verbose=False):
    """
        Return the estimated level on the given date at the given location.
        The level get's estimated by sinusoidal interpolation between extreme
        tide levels. Returns float.
    """
    tide = getTide(date, location, verbose)
    print tide
    dates = [item[0] for item in tide]
    # determine which transition to take
    a, b = None, None
    for i in range(len(dates)-1):
        if date > dates[i] and date < dates[i+1]:
            a = tide[i]
            b = tide[i+1]
    # set variables
    adate = a[0]
    alevel = a[1]
    astate = a[2]
    bdate = b[0]
    blevel = b[1]
    # compute level by interpolation
    level = sinterp(date=date,
                    lastextremedate=adate,
                    deltatonext=bdate-adate,
                    low=min(alevel, blevel),
                    hub=abs(max(alevel, blevel)-min(alevel, blevel)),
                    rising=(not astate),
                    verbose=verbose)
    if verbose:
        print 'level:', level
    # return result
    return level

def sinterp(date, lastextremedate, deltatonext, low, hub, rising=True, verbose=False):
    """
        Interpolates a point between two extreme tide levels
        by using a simple sinus slope. Returns the interpolate level
        as float.
    """
    # offset from date to the last extreme date
    deltatolast = date-lastextremedate
    # the factor from the date to pi scale
    factor = deltatolast.seconds/float(deltatonext.seconds)
    # the mapping into the pi scale
    x = np.pi*factor
    # rising(True) or falling slope(False)
    if rising:
        phase = -1
    else:
        phase = 1
    # return the interpolation with sinus flank
    result = (np.sin(x+phase*(.5*np.pi))+1)*.5*hub+low
    if verbose:
        print 'interpolating'
        print '    date:', date
        print '    deltatolast:', deltatolast
        print '    deltatonext:', deltatonext 
        print '    factor:', factor
        print '    x:', x
        print '    result:', result
    return result


def plotLevels(date=datetime.datetime.now(), location=1208, now=True, verbose=False):
    """
        Plot the tide levels of the given date at the given location.
    """
    # fetch tide info [(date, level, state),...]
    tide = getTide(date, location, verbose)
    
    # pretty info
    if verbose:
        print 'tide levels on', datetime.datetime.strftime(date, '%d.%m.%Y'), 'at %s' % location
        for item in tide:
            print '   ', item   
    
    # there may be 3 or 4 extreme levels on one date: 3 <= len(tide) <= 4
    # the sequence of the extreme levels alternates
    # but may start with either high or low tide
    # hence non speaking names
    dates = map(lambda x: x[0], tide)
    levels = map(lambda x: x[1], tide)
    states = map(lambda x: x[2], tide)
    if len(tide) == 4:
        adate, bdate, cdate, ddate = dates
        alevel, blevel, clevel, dlevel = levels
    else:
        assert len(tide) == 3, 'length of tide is %s' % len(tide)
        adate, bdate, cdate = dates
        alevel, blevel, clevel = levels
    
    # setup plot
    fig, ax = plt.subplots(1)
    fig.autofmt_xdate()
    ax.fmt_xdata = mdates.DateFormatter('%Y-%m-%d')    
    
    # do the actual plotting
    ## plot the transitions
    n = 25
    for i in range(len(tide)-1):
        firstdate = dates[i]
        seconddate = dates[i+1]
        firstlevel = levels[i]
        secondlevel = levels[i+1]
        firststate = states[i]
        
        x = np.array([firstdate]*n) + np.array([(seconddate-firstdate)/n]*n) * np.arange(n)
        x = np.append(x, seconddate)
        u = lambda x: sinterp(date=x,
                              lastextremedate=firstdate,
                              deltatonext=seconddate-firstdate,
                              low=min(firstlevel, secondlevel),
                              hub=abs(max(firstlevel, secondlevel)-min(firstlevel, secondlevel)),
                              rising=(not firststate))
        plt.plot(x, map(u, x), 'r-')
    
    ## plot now
    if now:
        # get now
        now = date
        # do now and the given date correspond?
        day_month_year = lambda date: datetime.datetime.strftime(date, '%d.%m.%Y')
        if day_month_year(now) == day_month_year(date):
            plt.vlines(now, ymin=-1, ymax=max(levels)+1, colors='g', label='asjkga')
            # estimate level
            nowlevel = level(now, location, verbose)
            plt.plot(now, nowlevel, 'bx')
            # annotate
            plt.text(now, nowlevel, '%s m' % round(nowlevel, 2))
            #plt.annotate(alpha % (alevel, hours_minutes(adate)), xy=(adate, alevel), xytext=(adate, alevel+.25), arrowprops=dict(facecolor='black', shrink=0.05),)
        else:
            print '"now" option not applicable, since the given date is not today'
    
    # set x-range
    today = datetime.datetime(date.year, date.month, date.day)
    tomorrow = today + datetime.timedelta(days=1)
    plt.axis([today, tomorrow, min(levels)-1, max(levels)+1])
    
    # make annotations regarding tide levels and time
    lowtide = 'low tide\n%s m\n%s h'
    hightide = 'high tide\n%s m\n%s h'
    if states[0] == 1:
        alpha = hightide
        beta = lowtide
    else:
        alpha = lowtide
        beta = hightide
    hours_minutes = lambda date: datetime.datetime.strftime(date, '%H:%M')
    plt.annotate(alpha % (alevel, hours_minutes(adate)), xy=(adate, alevel), xytext=(adate, alevel+.25), arrowprops=dict(facecolor='black', shrink=0.05),)
    plt.annotate(beta % (blevel, hours_minutes(bdate)), xy=(bdate, blevel), xytext=(bdate, blevel+.25), arrowprops=dict(facecolor='black', shrink=0.05),)
    plt.annotate(alpha % (clevel, hours_minutes(cdate)), xy=(cdate, clevel), xytext=(cdate, clevel+.25), arrowprops=dict(facecolor='black', shrink=0.05),)
    if len(tide) == 4:
        plt.annotate(beta % (dlevel, hours_minutes(ddate)), xy=(ddate, dlevel), xytext=(ddate, dlevel+.25), arrowprops=dict(facecolor='black', shrink=0.05),)
    
    # set title, labels and show plot
    plt.title('%s, %s' % (listLocations()[1][location], date.strftime('%d.%m.%Y')))
    plt.xlabel('time')
    plt.ylabel('water level in meters')
    plt.grid(True)
    ax.set_aspect('auto')
    plt.show()
    
def maxLevel(date=datetime.datetime.now(), location=1208, verbose=False):
    tide = getTide(date, location, verbose)
    return max([item[1] for item in tide])

def minLevel(date=datetime.datetime.now(), location=1208, verbose=False):
    tide = getTide(date, location, verbose)
    return min([item[1] for item in tide])
    
if __name__ == '__main__':
    # print general info
    print '### Tide table screen scrape at www.gezeiten-kalender.de ###'
    print '    check options "-h" or "--help" for usage details\n'

    # check if the url of the tide calendar is reachable at all 
    if not calenderReachable():
        print TIDE_URL, 'unreachable! will exit.'
        # if not, exit
        sys.exit()
        
    # set up the opt parser
    parser = optParser()
    (options, args) = parser.parse_args()

    # list Europe locations if told so
    if options.list_locations:
        listLocations(verbose=True)
        # and exit
        sys.exit()
    
    # get the location from the options
    location = int(options.location)
    # parse the date from the options
    dateformat = '%d-%m-%Y'
    ## append if hours and minutes are given as well
    if ':' in options.date:
        dateformat += '-%H:%M'
    date = datetime.datetime.strptime(options.date, dateformat)
    
    # actual call to the tide function
    getTide(date, location, verbose=True)
    
    # also plot if told so
    if options.plot:
        plotLevels(date, location)