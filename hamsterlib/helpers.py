from collections import namedtuple
import re
import datetime
from gettext import gettext as _


TimeFrame = namedtuple('Timeframe', ('start_date', 'start_time',
    'end_date', 'end_time', 'offset'))


def get_day_end(config):
    """
    Get the day end time given the day start. This assumes full 24h day.

    Args:
        config (dict): Configdict. Needed to extract ``day_start``.

    Note:
        This is merely a convinience funtion so we do not have to deduct this from ``day_start``
        by hand all the time.
    """
    day_start_datetime = datetime.datetime.combine(datetime.date.today(), config['day_start'])
    day_end_datetime = day_start_datetime - datetime.timedelta(seconds=1)
    return day_end_datetime.time()


def end_day_to_datetime(end_day, config):
    """
    Convert a given end day to its proper datetime.

    This is non trivial because of variable ``day_start``s. We want to make sure
    that even if an 'end day' is specified the actual point in time may reach into the following
    day.

    Args:
        end (datetime.date): Raw end date that is to be adjusted.
        config: Controler config containing information on when a workday starts.

    Returns:
        datetime.datetime: The endday as a adjusted datetime object.

    Example:
        Given a ``day_start`` of ``5:30`` and end date of ``2015-04-01`` we actually want to
        consider even points in time up to ``2015-04-02 5:29``. That is to represent that a
        *work day*
        does not match *calendar days*.
    """

    day_start_time = config['day_start']
    day_end_time = get_day_end(config)

    if day_start_time == datetime.time(0, 0, 0):
        end = datetime.datetime.combine(end_day, day_end_time)
    else:
        end = datetime.datetime.combine(end_day, day_end_time) + datetime.timedelta(days=1)
    return end


def parse_time_range(time_info):
    """
    Generic parser for time(-range) information.

    Args:
        time_info (str): Raw string containing encoded timespan information.
            Date/Time-combinations are expected in a ``YYYY-MM-DD hh:mm`` format.
            Relative  times can be given with ``-minutes``.
            Please note that either *relative* or *absolute* times will be considered.

    Returns:
        TimeFrame: Tuple that provides convinient access to all seperate elements
            extracted from the raw string.

    Note:
        * Relative times always return just ``(None, None, None, None, timedelta)``.
    """

    # [TODO] Add a list of supported formats.

    # Credits to tbaugis (https://github.com/tbaugis) for the original
    # implementation in hamster-cli.

    def get_time(time):
        if time:
            time = datetime.datetime.strptime(time.strip(), "%H:%M").time()
        return time

    def get_date(date):
        if date:
            date = datetime.datetime.strptime(date.strip(), "%Y-%m-%d").date()
        return date

    patterns = (
        '^((?P<relative>-\d.+)?|('
        '(?P<date1>\d{4}-\d{2}-\d{2})?'
        '(?P<time1> ?\d{2}:\d{2})?'
        '(?P<dash> ?-)?'
        '(?P<date2> ?\d{4}-\d{2}-\d{2})?'
        '(?P<time2> ?\d{2}:\d{2})?)?)'
        '(?P<rest>\D.+)?$'
    )
    result = TimeFrame(None, None, None, None, None)
    match = re.compile(patterns).match(time_info)
    if match:
        fragments = match.groupdict()

        if fragments['relative']:
            try:
                result = TimeFrame(None, None, None, None,
                    datetime.timedelta(minutes=abs(int(fragments['relative']))))
            except ValueError as e:
                raise ValueError(_(
                    "It seems you provided more than just a relative time"
                    " Please check your time_info string. You can only use relative OR"
                    " absolute time statements."
                ))
        else:
            result = TimeFrame(
                start_date=get_date(fragments.get('date1', None)),
                start_time=get_time(fragments.get('time1', None)),
                end_date=get_date(fragments.get('date2', None)),
                end_time=get_time(fragments.get('time2', None)),
                offset=None
            )
    return result


def complete_timeframe(timeframe, config):
    """Apply fallback strategy to incomplete timeframes."""

    def complete_start_date(date):
        """
        Assign default if ``date=None``, else ensure its a ``datetime.date`` instance.

        Args:
            date (datetime.date): Startdate information.

        Returns:
            datetime.date: Either the original date or the default solution.

        Raises:
            TypeError: If ``date``` is neither ``None`` nor  ``datetime.date`` instance.

        Note:
            Reference behavior taken from [hamster-cli](https://github.com/projecthamster/
            hamster/blob/master/src/hamster-cli#L368).
        """

        if not date:
            date = datetime.date.today()
        else:
            if not isinstance(date, datetime.date):
                raise TypeError(_(
                    "Expected datetime.date instance, got {type} instead.".format(
                        type=type(date))
                ))
        return date

    def complete_start_time(time, day_start):
        if not time:
            time = day_start
        else:
            if not isinstance(time, datetime.time):
                raise TypeError(_(
                    "Expected datetime.time instance, got {type} instead.".format(
                        type=type(time))
                ))
        return time

    def complete_start(date, time, config):
        return datetime.datetime.combine(
            complete_start_date(timeframe.start_date),
            complete_start_time(timeframe.start_time, config['day_start']),
        )

    def complete_end_date(date):
        if not date:
            date = datetime.date.today()
        else:
            if not isinstance(date, datetime.date):
                raise TypeError(_(
                    "Expected datetime.date instance, got {type} instead.".format(
                        type=type(date))
                ))
        return date

    def complete_end(date, time, config):
        date = complete_end_date(date)
        if time:
            result = datetime.datetime.combine(date, time)
        else:
            result = end_day_to_datetime(date, config)
        return result

    if not timeframe.offset:
        start = complete_start(timeframe.start_date, timeframe.start_time, config)
    else:
        start = datetime.datetime.now() - timeframe.offset

    end = complete_end(timeframe.end_date, timeframe.end_time, config)
    return (start, end)


def parse_time(time):
    """
    Parse a date/time string and return a corresponding datetime object.

    Args:
        time (str): A ``string` of one of the following formats: ``%H:%M``, ``%Y-%m-%d`` or
            ``%Y-%m-%d %H:%M``.

    Returns:
        datetime.datetime: Depending on input string either returns ``datetime.date``,
            ``datetime.time`` or ``datetime.datetime``.

    Raises:
        ValueError: If ``time`` can not be matched against any of the accepted formats.
    """

    # [TODO]
    # Propably should enhance error handling for invalid but correctly formated
    # times such as '30:55' or '2015-15-60'.

    length = len(time.strip().split())
    if length == 1:
        try:
            result = datetime.datetime.strptime(time, '%H:%M').time()
        except ValueError:
            result = datetime.datetime.strptime(time, '%Y-%m-%d').date()
    elif length == 2:
        result = datetime.datetime.strptime(time, '%Y-%m-%d %H:%M')
    else:
        raise ValueError(_(
            "Sting does not seem to be in one of our supported time formats."
        ))
    return result