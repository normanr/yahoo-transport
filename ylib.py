#!/usr/bin/python

# Yahoo driver test script.
from yahoo_helpers import *
import socket, time
import avatar
import pprint
import re
import random
import httplib
import urllib
import md5
import base64
from string import maketrans

base64translate = maketrans('+/=', '._-')


def printpacket(packet):
    s,u = ymsg_dehdr(packet)
    t = ymsg_deargu(u[:s[2]])
    print 'send', s, pprint.pformat(t), len(packet)


# Yahoo Functions
class YahooCon:
    rbuf = ''
    roster_tmp = ''
    pripingtime = 0
    secpingtime = 0
    confpingtime = 0
    pripingobj = None
    secpingobj = None
    confpingojb = None
    session = 0
    host = 'cs1.msg.dcn.yahoo.com'
    hostlist = socket.gethostbyname_ex('scs.msg.yahoo.com')[2]
    #hostlist = ['cs1.msg.dcn.yahoo.com','cs2.msg.dcn.yahoo.com','cs3.msg.dcn.yahoo.com','cs4.msg.dcn.yahoo.com','cs5.msg.dcn.yahoo.com','cs6.msg.dcn.yahoo.com','cs7.msg.dcn.yahoo.com','cs8.msg.dcn.yahoo.com','cs9.msg.dcn.yahoo.com','cs10.msg.dcn.yahoo.com','cs11.msg.dcn.yahoo.com','cs12.msg.dcn.yahoo.com','cs13.msg.dcn.yahoo.com','cs14.msg.dcn.yahoo.com','cs15.msg.dcn.yahoo.com','cs16.msg.dcn.yahoo.com','cs17.msg.dcn.yahoo.com','cs18.msg.dcn.yahoo.com','cs40.msg.dcn.yahoo.com','cs41.msg.dcn.yahoo.com','cs42.msg.dcn.yahoo.com','cs43.msg.dcn.yahoo.com','cs44.msg.dcn.yahoo.com','cs45.msg.dcn.yahoo.com','cs46.msg.dcn.yahoo.com','cs50.msg.dcn.yahoo.com','cs51.msg.dcn.yahoo.com','cs52.msg.dcn.yahoo.com']
    port = 5050
    version = 0x00100000
    sock = None
    # a dictionary of groups and members
    buddylist = {}
    # Tuple by availabilaity, show value, status message
    roster = {}
    handlers = {}
    # login -- on sucessful login
    # loginfail -- on login failure

    def __init__(self, username, password, fromjid,fromhost,dumpProtocol):
        self.username = username
        self.password = password
        self.fromhost = fromhost
        self.fromjid = fromjid
        self.roster = {}
        self.buddylist = {}
        self.away = False
        #variables for public MUC
        self.alias = username
        #Each room has a list of participants in the form of {username:(alias,state,statemsg)}
        self.roomlist = {}
        self.roomnames = {} #Dictionary entry for *NAUGHTY* clients that lowercase the JID
        self.chatlogin = False
        self.chatresource = None
        #login junk
        self.connok = False
        self.conncount = 0
        self.cookies = []
        self.resources = {}
        self.xresources = {}
        self.offset = int(random.random()*len(self.hostlist))
        self.dumpProtocol = dumpProtocol

    # utility methods
    def connect(self):
        self.connok=False
        while self.conncount != len(self.hostlist):
            if self.dumpProtocol: print "conncount", self.conncount
            self.sock = None
            self.sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            self.sock.bind((self.fromhost,0))
            try:
                if not self.sock.connect((self.hostlist[(self.offset+self.conncount)%len(self.hostlist)],self.port)):
                    self.conncount = self.conncount + 1
                    return self.sock
            except socket.error:
                self.conncount = self.conncount + 1
                pass
        return None

    def moreservers(self):
        if self.conncount < len(self.hostlist):
            if self.dumpProtocol: print "more servers %s %s" % (len(self.hostlist),self.conncount)
            return True
        else:
            return False

    def y_parsebuddies(self,txt):
        lines = txt.split('\n')
        #print lines

        #print "Before: ",self.roster
        for each in lines:
            try:
                group, members = each.split(':')
                self.buddylist[group] = []
                for e in members.split(','):
                    self.buddylist[group].append(e)
                    if not self.roster.has_key(e):
                        self.roster[e]=('unavailable',None, None)
            except ValueError:
                pass
        #print "After: ", self.roster

    # decoding handlers
    def ymsg_challenge(self,hdr,pay):
        # send authentication challenge responce
        session = hdr[5]
        self.session=session
        chalstr = pay[0][94]

        # Do HTTPS login.
        h = httplib.HTTPSConnection('login.yahoo.com')
        params = urllib.urlencode({
            'src': 'ymsgr',
            'login': self.username,
            'passwd': self.password,
            'chal': chalstr})
        h.request('GET', '/config/pwtoken_get?%s' % params)
        resp = ('code=' + h.getresponse().read()).splitlines()
        if self.dumpProtocol: print "HTTPS pwtoken_get response: %r" % resp
        resp = dict([x.split('=', 1) for x in resp])

        code = resp['code']
        if code != '0':
            # Interpret login problems.  These should broken out into individual conditionals and given
            # more specific messages in yahoo.py.
            if code == '100' or code == '1212' or code == '1235':
                # Username or password is missing (100), username or password is incorrect (1212),
                # or username does not exist (1235).
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'badpassword')
                return None

            elif code == '1013':
                # Username contains @yahoo.com or similar which needs removing.
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'badusername')
                return None

            elif code == '1213' or code == '1214' or code == '1236' or code == '1218':
                # Security lock on account due to failed login attempts (1213 and 1236), general security
                # lock (1214), or account deactivated by Yahoo! (1218).
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'locked')
                return None

            else:
                # Other error not listed.
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self)
                return None

        # No error in code, so login successful, grab our crumb.
        params = urllib.urlencode({
            'src': 'ymsgr',
            'token': resp['ymsgr']})
        h.request('GET', '/config/pwtoken_login?%s' % params)
        resp = ('code=' + h.getresponse().read()).splitlines()
        if self.dumpProtocol: print "HTTPS pwtoken_login response %r" % resp
        resp = dict([x.split('=', 1) for x in resp])

        # Calculate hash of crumb and challenge string.
        mhash = md5.new()
        mhash.update(resp['crumb'])
        mhash.update(chalstr)
        bhash = base64.b64encode(mhash.digest()).translate(base64translate)

        # Assemble response packet.
        npay = ymsg_mkargu({
            1:   self.username,
            0:   self.username,
            277: resp['Y'],
            278: resp['T'],
            307: bhash,
            244: '2097087',
            2:   self.username,
            2:   '1',
            98:  'us',
            135: '9.0.0.1389'})
        nhdr = ymsg_mkhdr(self.version,len(npay),Y_challenge,0x5a55aa55,self.session)
        return nhdr+npay

    def ymsg_login(self,hdr,pay):
        # process login packet
        if pay[0].has_key(87):
            self.roster_tmp += pay[0][87]
        if self.roster_tmp and ( hdr[4] == 0 or not pay[0].has_key(87) ):
            self.y_parsebuddies(self.roster_tmp)
            self.roster_tmp = ''
        if pay[0].has_key(89):
            self.aliases = pay[0][89].split(',')
        for each in pay:
            if pay[each].has_key(59):
                self.cookies.append(pay[each][59])
        #print "got to login handler"
        if self.handlers.has_key('login'):
            self.handlers['login'](self)
        #pay = ymsg_mkargu({109:self.username})
        #hdr = ymsg_mkhdr(self.version,len(pay),Y_ping,1,self.session)
        #return self.sock.send(hdr+pay)

    def ymsg_online(self,hdr,pay):
        if pay[0].has_key(7):
            for each in pay:
                typ = None
                status = None
                if pay[each].has_key(10):
                    (typ, status) = self.determine_typ_status(pay[each])

                if pay[each].has_key(7):
                    self.roster[pay[each][7]]=('available', typ, status)
                    if pay[each].has_key(198):
                        if pay[each][198] == '1' and pay[each].has_key(197):
                            b = avatar.getavatar(pay[each][7], self.dumpProtocol)
                            if b != None and self.handlers.has_key('avatar'):
                                self.handlers['avatar'](self,pay[each][7],b)
                        elif pay[each][198] == '0':
                            if self.handlers.has_key('avatar'):
                                self.handlers['avatar'](self,pay[each][7],None)
                    if pay[each].has_key(13):
                        i = int(pay[each][13])
                        j = i%4
                        k= j%2
                        if i/4:
                            if self.dumpProtocol: print "contact is on games"
                        if j/2:
                            if not self.resources.has_key(pay[each][7]):
                                self.resources[pay[each][7]]=[]
                            if self.resources.has_key(pay[each][7]):
                                if not 'chat' in self.resources[pay[each][7]]:
                                    self.resources[pay[each][7]].append('chat')
                            if self.handlers.has_key('chatonline'):
                                self.handlers['chatonline'](self,pay[each][7])
                        if k:
                            if not self.resources.has_key(pay[each][7]):
                                self.resources[pay[each][7]]=[]
                            if self.resources.has_key(pay[each][7]):
                                if not 'messenger' in self.resources[pay[each][7]]:
                                    self.resources[pay[each][7]].append('messenger')
                            if self.handlers.has_key('online'):
                                self.handlers['online'](self,pay[each][7])

    def ymsg_avatar(self,hdr,pay):
        if pay[0].has_key(4):
            for each in pay:
                if pay[each].has_key(4):
                    if pay[each].has_key(198):
                        if pay[each][198] == '1' and pay[each].has_key(197):
                            b = avatar.getavatar(pay[each][197], self.dumpProtocol)
                            if b != None and self.handlers.has_key('avatar'):
                                self.handlers['avatar'](self,pay[each][4],b)
                        elif pay[each][198] == '0':
                            if self.handlers.has_key('avatar'):
                                self.handlers['avatar'](self,pay[each][4],None)

    def ymsg_imvset(self,hdr,pay):
        if pay[0].has_key(7):
            for each in pay:
                if pay[each].has_key(13):
                    if pay[each][13] == '1':
                        if pay[each].has_key(7):
                            self.roster[pay[each][7]]=('available', None, None)
                            if self.handlers.has_key('online'):
                                self.handlers['online'](self,pay[each][7])

    def ymsg_offline(self,hdr,pay):
        if pay[0].has_key(7):
            for each in pay:
                if pay[each].has_key(7):
                    #self.roster[pay[each][7]]=('unavailable', None, None)
                    if pay[each].has_key(13):
                        i = int(pay[each][13])
                        j = i%4
                        k= j%2
                        if i/4:
                            if self.dumpProtocol: print "contact is off games"
                        if not j/2:
                            if self.resources.has_key(pay[each][7]):
                                if 'chat' in self.resources[pay[each][7]]:
                                    self.resources[pay[each][7]].remove('chat')
                                    if self.handlers.has_key('chatoffline'):
                                        self.handlers['chatoffline'](self,pay[each][7])
                        if not k:
                            if self.resources.has_key(pay[each][7]):
                                if 'messenger' in self.resources[pay[each][7]]:
                                    self.resources[pay[each][7]].remove('messenger')
                                    if self.handlers.has_key('offline'):
                                        self.handlers['offline'](self,pay[each][7])
                    if not self.resources.has_key(pay[each][7]) or self.resources[pay[each][7]] == []:
                        self.roster[pay[each][7]]=('unavailable', None, None)
                        if self.handlers.has_key('offline'):
                            self.handlers['offline'](self,pay[each][7])

        elif len(pay[0].keys()) == 0:
            if self.handlers.has_key('closed'):
                self.handlers['closed'](self)

    def ymsg_notification(self,hdr,pay):
        if pay[0].has_key(20):
            url = pay[0][20]
        else:
            url = None
        if pay[0].has_key(14):
            desc = pay[0][14]
        else:
            desc = None
        if self.handlers.has_key('calendar'):
            self.handlers['calendar'](self,url,desc)

    def ymsg_email(self,hdr,pay):
        if pay[0].has_key(43):
            fromtxt = pay[0][43]
        else:
            fromtxt = None
        if pay[0].has_key(42):
            fromaddr = pay[0][42]
        else:
            fromaddr = None
        if pay[0].has_key(18):
            subj = pay[0][18]
        else:
            subj = None
        if subj != None or fromaddr != None or fromtxt != None:
            if self.handlers.has_key('email'):
                self.handlers['email'](self,fromtxt,fromaddr,subj)

    def determine_typ_status(self, msg):
        status = None
        typ = None
        if msg.has_key(10):
            if msg[10] == '1':
                typ, status = "away", "Be Right Back"
            elif msg[10] == '2':
                typ, status = "dnd", "Busy"
            elif msg[10] == '3':
                typ, status = "xa", "Not at Home"
            elif msg[10] == '4':
                typ, status = "away", "Not at my Desk"
            elif msg[10] == '5':
                typ, status = "xa", "Not in the office"
            elif msg[10] == '6':
                typ, status = "dnd", "On the phone"
            elif msg[10] == '7':
                typ, status = "away", "On Vacation"
            elif msg[10] == '8':
                typ, status = "away", "Out to lunch"
            elif msg[10] == '9':
                typ, status = "away", "Stepped Out"
            elif msg[10] == '99':
                if msg.has_key(19):
                    status = re.sub('\x05','',unicode(msg[19],'utf-8','replace'))
                else:
                    status = None
                typ = None
                if msg.has_key(47):
                    if msg[47] == '1':
                        typ = "dnd"
                    elif msg[47] == '2':
                        typ = "away"
            elif msg[10] == '999':
                typ = "away"
                status = None
        return (typ, status)

    def ymsg_away(self,hdr,pay):
        if pay[0].has_key(10):
            (typ, status) = self.determine_typ_status(pay[0])
            if pay[0].has_key(7):
                self.roster[pay[0][7]]=("available",typ,status)
                if self.handlers.has_key('online'):
                    self.handlers['online'](self,pay[0][7])

    def ymsg_back(self,hdr,pay):
        if pay[0].has_key(10):
            (typ, status) = self.determine_typ_status(pay[0])
            if pay[0].has_key(7):
                self.roster[pay[0][7]]=('available',typ,status)
                if self.handlers.has_key('online'):
                    self.handlers['online'](self,pay[0][7])


    def ymsg_roster(self,hdr,pay):
        if pay[0].has_key(3):
            if pay[0].has_key(14):
                msg = pay[0][14]
            else:
                msg = ''
            if self.handlers.has_key('subscribe'):
                self.handlers['subscribe'](self,pay[0][3],msg)
        self.ymsg_online(hdr,pay)

    def ymsg_addbuddy(self,hdr,pay):
        pass

    def ymsg_msg(self, hdr, pay):
        for each in pay.keys():
            if pay[each].has_key(14):
                if pay[each].has_key(124):
                    if pay[each][124]=='2':
                        msg = '/me '+pay[each][14]
                else:
                    msg = pay[each][14]
                if pay[each].has_key(15):
                    ts = pay[each][15]
                else:
                    ts = None
                if hdr[3] == Y_msg:
                    if hdr[4] == 2:
                        if self.handlers.has_key('messagefail'):
                            self.handlers['messagefail'](self, pay[each][4], msg, ts)
                    else:
                        if self.handlers.has_key('message'):
                            self.handlers['message'](self, pay[each][4], msg, ts)
                if hdr[3] == Y_confpm:
                    if self.handlers.has_key('chatmessage'):
                        self.handlers['chatmessage'](self,pay[each][4], msg, ts)

    def ymsg_notify(self, hdr, pay):
        for each in pay.keys():
            if pay[each].has_key(13):
                if self.handlers.has_key('notify'):
                    self.handlers['notify'](self,pay[each][4],pay[each][13]=='1')

    def ymsg_ping(self, hdr, pay):
        self.secpingfreq = 60
        self.pripingfreq = 4
        if pay[0].has_key(143):
            self.secpingfreq = float(pay[0][143])
        else:
            self.secpingfreq = None
        if pay[0].has_key(144):
            self.pripingfreq = float(pay[0][144])
        else:
            self.pripingfreq = None
        if self.handlers.has_key('ping'):
            self.handlers['ping'](self)

    def ymsg_reqroom(self, hdr,pay):
        if self.dumpProtocol: print "got reqroom"
        if self.handlers.has_key('reqroom'):
            self.handlers['reqroom'](self.fromjid)

    def ymsg_conflogon(self,hdr,pay):
        if self.handlers.has_key('conflogon'):
            self.handlers['conflogon']()

    def ymsg_joinroom(self,hdr,pay):
        # Do generic room information stuff
        room = None
        roominfo = {}
        if pay[0].has_key(104):
            roominfo['room'] = pay[0][104]
            room = pay[0][104]
        if pay[0].has_key(105):
            roominfo['topic'] = pay[0][105]
        if pay[0].has_key(108):
            roominfo['members'] = pay[0][108]
        if roominfo != {}:
            if self.handlers.has_key('roominfo') and room != None:
                self.handlers['roominfo'](self.fromjid, roominfo)
        # Do room member stuff
        for b in pay:
            each = pay[b]
            a = {}
            if each.has_key(109):
                a['yip']=each[109]
            if each.has_key(141):
                a['nick']=each[141]
            if each.has_key(113):
                a['ygender'] = each[113]
            if each.has_key(110):
                a['age'] = each[110]
            if each.has_key(142):
                a['location'] = each[142]
                a['location'] = each[142]
            if self.handlers.has_key('chatjoin') and room != None:
                self.handlers['chatjoin'](self.fromjid,room,a)

    def ymsg_leaveroom(self,hdr,pay):
        room = None
        if pay[0].has_key(104):
            room = pay[0][104]
        for a in pay:
            each = pay[a]
            if each.has_key(109):
                yid = each[109]
            else:
                yid = None
            if each.has_key(141):
                nick = each[141]
            else:
                nick = yid
            if self.handlers.has_key('chatleave'):
                self.handlers['chatleave'](self.fromjid,room,yid,nick)


    def ymsg_roommsg(self, hdr, pay):
        if pay[0].has_key(109):
            if pay[0].has_key(124):
                if pay[0][124]=='2':
                    msg = '/me '+pay[0][117]
                else:
                    msg = pay[0][117]
            else:
                msg = pay[0][117]
            if hdr[4] == 1:
                if self.handlers.has_key('roommessage'):
                    self.handlers['roommessage'](self, pay[0][109], pay[0][104], msg)
            elif hdr[4] == 2:
                if self.handlers.has_key('roommessagefail'):
                    self.handlers['roommessagefail'](self, pay[0][109], pay[0][104], msg)

    def ymsg_buddylist15(self, hdr, pay):
        # Loop through the payload entries and pull out groups and buddy names.  The odd loop construct is to make
        # sure the entries are parsed in order; I'm not convinced (yet) that dict's .values() will always iterate
        # in the desired order.
        group = 'Top Level'
        i = 0
        while pay.has_key(i):
            entry = pay[i]
            i = i + 1

            if YB_type not in entry:
                continue
            typ = int(entry[YB_type])

            # Entry is a group.
            if typ == YBT_group and YB_groupname in entry:
                group = entry[YB_groupname]
                self.buddylist[group] = []

            # Entry is a buddy.
            if typ == YBT_buddy and YB_buddyname in entry:
                buddy = entry[YB_buddyname]
                fed = None
                if YB_cloud in entry:
                    fed = int(entry[YB_cloud])

                #skeeziks:
                # Ignore MSN contacts for now.  Message receipt seems to work but sending is non-functional, at
                # least in my tests.  I've also had reports of presence not really working.  Feel free to
                # comment this out if you wish to play with it.
                #normanr:
                # Changed to detect federation network id (from pidgin).  To make return messages work you need
                # to send the federation network id too, so you have to mangle the buddyname to support it.
                # (pidgin prepends msn/ to the buddy name, but xmpp doesn't allow /'s in bare jids,
                #  so we'd need to pick another method of mangling the jid - maybe msn^buddyname?)
                if fed:
                    continue

                self.buddylist[group].append(buddy)
                if not self.roster.has_key(buddy):
                    self.roster[buddy]=('unavailable',None, None)
                if self.handlers.has_key('subscribe'):
                    self.handlers['subscribe'](self, buddy, '')

    def ymsg_statusupdate15(self, hdr, pay):
        # If we're here then buddy is online in some sense.  Let's figure out how online they are.  This message may
        # contain more than one buddy status (this seems to happen right after login).
        for entry in pay.values():
            if YB_buddyname not in entry or YB_status not in entry:
                continue

            buddy = entry[YB_buddyname]
            typ = int(entry[YB_status])
            fed = None
            if YB_cloud in entry:
                fed = int(entry[YB_cloud])

            # Ignore MSN contacts for now.  See similar comment in ymsg_cloud() for rationale.
            if fed:
                continue

            # Grab status message, if any.
            status = ''
            if YB_statusmessage in entry:
                status = entry[YB_statusmessage]

            # Determine idle/away status.
            away = 0
            idle = 0
            if typ > 0 and typ < 12:
                away = 1
            if entry.has_key(47) and int(entry[47]) > 0:
                away = 1
            if typ == 999:
                idle = 1

            # Update roster and presence.
            if typ < 1000 and typ != 12:
                # Buddy is online...
                if away == 1:
                    # ... but away.
                    self.roster[buddy] = ('available', 'dnd', status)
                elif idle == 1:
                    # ... but idle.
                    self.roster[buddy] = ('available', 'away', status)
                else:
                    # ... and not idle or away.
                    self.roster[buddy] = ('available', None, status)

                if self.handlers.has_key('online'):
                    self.handlers['online'](self, buddy, '')
            else:
                # Buddy is offline.
                self.roster[buddy] = ('unavailable', None, None)
                if self.handlers.has_key('offline'):
                    self.handlers['offline'](self, buddy)

    def ymsg_init(self):
        try:
            challenge = self.ymsg_send_challenge()
            if self.dumpProtocol: printpacket(challenge)
            return self.sock.send(challenge)
        except:
            if self.handlers.has_key('loginfail'):
                self.handlers['loginfail'](self)

    def ymsg_send_init(self):
        return ymsg_mkhdr(self.version,0,Y_init,0,0)

    def ymsg_send_challenge(self):
        pay = ymsg_mkargu({1:self.username})
        hdr = ymsg_mkhdr(self.version,len(pay),Y_chalreq,0,self.session)
        pkt = hdr + pay
        return pkt

    def ymsg_send_addbuddy(self, nick, msg=''):
        if msg == None:
            msg = ''
        pay = ymsg_mkargu({1:self.username,7:nick,65:"jabber_yt",14:msg})
        hdr = ymsg_mkhdr(self.version, len(pay), Y_rosteradd,1,self.session)
        return hdr+pay

    def ymsg_send_conflogon(self):
        if self.dumpProtocol: print "cookies",self.cookies
        pay = ymsg_mkargu({0:self.username,1:self.username,6: '%s; %s' % (self.cookies[0].replace('\t','=').split(';')[0],self.cookies[1].replace('\t','=').split(';')[0])})
        hdr = ymsg_mkhdr(self.version,len(pay),Y_confon,0x5a55aa55,self.session)
        return hdr+pay

    def ymsg_send_conflogoff(self):
        pay = ymsg_mkargu({0:self.username,1:self.username})
        hdr = ymsg_mkhdr(self.version,len(pay),Y_confoff,0,self.session)
        return hdr+pay

    def ymsg_send_chatlogin(self,alias):
        if alias == None:
            alias == self.username
        self.alias = alias
        pay = ymsg_mkargu({109:self.username,1:self.username,6:'abcde'})
        hdr = ymsg_mkhdr(self.version, len(pay), Y_reqroom,0,self.session)
        return hdr+pay

    def ymsg_send_chatlogout(self):
        pay = ymsg_mkargu({1:self.username})
        hdr = ymsg_mkhdr(self.version, len(pay), Y_chatlogout, 0, self.session)
        return hdr+pay

    def ymsg_send_chatjoin(self,room):
        self.roomlist[room]={'byyid':{},'bynick':{},'info':{}}
        pay = ymsg_mkargu({1:self.username, 62:'2',104:room})
        hdr = ymsg_mkhdr(self.version,len(pay), Y_joinroom,0,self.session)
        return hdr+pay

    def ymsg_send_chatleave(self,room):
        pay = ymsg_mkargu({1:self.username,104:room})
        hdr = ymsg_mkhdr(self.version,len(pay), Y_leaveroom, 1, self.session)
        return hdr+pay

    def ymsg_send_roommsg(self,room,msg, type = 0):
        pay = ymsg_mkargu({1:self.username,104:room,117:msg,124:type})
        hdr = ymsg_mkhdr(self.version,len(pay), Y_chtmsg,1,self.session)
        return hdr+pay

    def ymsg_send_message(self, nick, msg):
        status = 0
        if self.roster.has_key(nick):
            if self.roster[nick][0] == 'unavailable':
                status = 0x5a55aa55
        else:
            status = 0x5a55aa55
        if msg[0:10]=='/me thinks':
            typ = 2
            msg = msg[10:]
        elif msg[0:3]=='/me':
            typ = 2
            msg = msg[3:]
        else:
            typ = 1
        msg = msg.replace('\n', '\r')
        pay = ymsg_mkargu({0:self.username, 1:self.username, 5:nick,14:msg})
        hdr = ymsg_mkhdr(self.version,len(pay), Y_msg,status,self.session)
        return hdr+pay

    def ymsg_send_chatmessage(self, nick, msg):
        status = 0
        if self.roster.has_key(nick):
            if self.roster[nick][0] == 'unavailable':
                status = 0x5a55aa55
        else:
            status = 0x5a55aa55
        if msg[0:10]=='/me thinks':
            typ = 2
            msg = msg[10:]
        elif msg[0:3]=='/me':
            typ = 2
            msg = msg[3:]
        else:
            typ = 1
        msg = msg.replace('\n', '\r')
        pay = ymsg_mkargu({0:self.username, 1:self.username, 5:nick,14:msg})
        hdr = ymsg_mkhdr(self.version,len(pay), Y_confpm,status,self.session)
        return hdr+pay

    def ymsg_send_notify(self, nick, state):
        pay = ymsg_mkargu({49:'TYPING', 1:self.username,14:' ',13:state, 5:nick,1002:'1',})
        hdr = ymsg_mkhdr(self.version,len(pay), Y_notify,0,self.session)
        return hdr+pay

    def ymsg_send_priping(self):
        if time.time() - self.pripingtime > 10:
            pay = ymsg_mkargu({109:self.username})
            hdr = ymsg_mkhdr(self.version,len(pay),Y_ping,1,self.session)
            self.pripingtime = time.time()
            return hdr+pay

    def ymsg_send_secping(self):
        if time.time() - self.secpingtime > 10:
            pay = ''
            hdr = ymsg_mkhdr(self.version,len(pay),Y_ping2, 1, self.session)
            self.secpingtime = time.time()
            return hdr+pay

    def ymsg_send_confping(self):
        if time.time() - self.confpingtime > 10:
            pay = ''
            hdr = ymsg_mkhdr(self.version,len(pay),Y_ping2, 1, self.session)
            self.confpingtime = time.time()
            return hdr+pay

    def ymsg_send_delbuddy(self, nick, msg=''):
        if msg == None:
            msg = ''
        bgroup = 'jabber_yt'
        for group in self.buddylist.keys():
            if nick in self.buddylist[group]:
                bgroup = group
        pay = ymsg_mkargu({1:self.username,7:nick,65:bgroup,14:msg})
        hdr = ymsg_mkhdr(self.version, len(pay), Y_rosterdel,0,self.session)
        return hdr+pay

    def ymsg_send_online(self, show = None, message = None):
        d = {}
        if message != None:
            d[19] = message.encode('utf-8','replace')
            d[10] = '99'
            d[47] = '0'
        else:
            d[10] = '0'
        if show == None:
            d[47] = '0'
        elif show == 'away':
            d[47] = '2'
        elif show == 'dnd':
            d[47] = '1'
        elif show == 'invisible':
            d[10]= '12'
        if self.dumpProtocol: print "send_online",d
        pay = ymsg_mkargu(d)
        hdr = ymsg_mkhdr(self.version,len(pay),Y_available,0,self.session)
        return hdr+pay

    def ymsg_send_back(self,msg=None):
        argu = {10:'0'}
        if msg != None:
            argu[19] = msg.encode('utf-8','replace')
            argu[10] = '99'
        argu[47] = '0'
        if self.dumpProtocol: print "send_back",argu
        pay = ymsg_mkargu(argu)
        hdr = ymsg_mkhdr(self.version,len(pay),Y_available,0,self.session)
        return hdr+pay

    def ymsg_send_away(self,show = None, msg=None):
        if msg != None:
            a={10:'99',19:msg.encode('utf-8','replace')}
        else:
            a={10:'1'}
        if show == None:
            a[47] = '0'
        elif show == 'away':
            a[47] = '2'
        elif show == 'dnd':
            a[47] = '1'
        elif show == 'invisible':
            a[10]= '12'
        if self.dumpProtocol: print "send_away",a
        pay = ymsg_mkargu(a)
        hdr = ymsg_mkhdr(self.version, len(pay), Y_away,0,self.session)
        return hdr+pay

    def ymsg_recv_challenge(self,hdr,pay):
        # Function to determine the error type and then send that to the main process
        if pay[0].has_key(66):
            #All the error cases are shown with a different code in the 66 field. Unfortunately we cannot process image ID at this time.
            if pay[0][66] == '3':
                #Bad username case
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'badusername')
            elif pay[0][66] == '13':
                #Bad password case
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'badpassword')
            elif pay[0][66] == '29':
                #Account requires image verify
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'imageverify')
            elif pay[0][66] == '14':
                #Account locked
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self,'locked')
            else:
                if self.handlers.has_key('loginfail'):
                    self.handlers['loginfail'](self)

    def Process(self):
        r = self.sock.recv(1024)
        #print r
        if len(r) != 0:
            self.rbuf = '%s%s'%(self.rbuf,r)
            #print len(self.rbuf)
        else:
            # Broken Socket Case.
            if self.handlers.has_key('closed'):
                self.handlers['closed'](self)
        while len(self.rbuf) >= 20:
            s,u = ymsg_dehdr(self.rbuf)
            if s[0] != 'YMSG' or s[2] < 0:
                if self.handlers.has_key('closed'):
                    self.handlers['closed'](self)
                    break
            size = 20+s[2]
            #print size, len(self.rbuf)
            if len(self.rbuf) >= size:
                try:
                    t = ymsg_deargu(u[:s[2]])
                except:
                    print "Broken connection Terminating"
                    if self.handlers.has_key('closed'):
                        self.handlers['closed'](self)
                if self.dumpProtocol: print 'recv', s, pprint.pformat(t), len(self.rbuf)
                if s[3] == Y_chalreq:           #87
                    # give salt
                    challenge = self.ymsg_challenge(s,t)
                    if challenge:
                        if self.dumpProtocol: printpacket(challenge)
                        self.sock.send(challenge)
                elif s[3] == Y_login:           #85
                    # login ok
                    self.ymsg_login(s,t)
                elif s[3] == Y_challenge:       #84
                    # login failed
                    self.ymsg_recv_challenge(s,t)
                elif s[3] == Y_online:          #1
                    self.ymsg_online(s,t)
                elif s[3] == Y_offline:         #2
                    self.ymsg_offline(s,t)
                elif s[3] == Y_confon:          #30
                    self.ymsg_online(s,t)
                elif s[3] == Y_confoff:         #31
                    self.ymsg_offline(s,t)
                elif s[3] == Y_roster:          #15
                    self.ymsg_roster(s,t)
                elif s[3] == Y_msg:             #6
                    self.ymsg_msg(s,t)
                elif s[3] == Y_confpm:      #32
                    self.ymsg_msg(s,t)
                elif s[3] == Y_notify:      #75
                    self.ymsg_notify(s,t)
                elif s[3] == Y_ping2:       #18
                    self.ymsg_ping(s,t)
                elif s[3] == Y_ping:        #161
                    self.ymsg_ping(s,t)
                elif s[3] == Y_rosteradd:     #131
                    self.ymsg_addbuddy(s,t)
                elif s[3] == Y_imvset:          #21
                    self.ymsg_imvset(s,t)
                elif s[3] == Y_away:            #3
                    self.ymsg_away(s,t)
                elif s[3] == Y_avatar:       #188
                    self.ymsg_avatar(s,t)
                elif s[3] == Y_statusupdate: #198
                    self.ymsg_away(s,t)
                #elif s[3] == Y_advstatusupdate: #199
                #    pass self.ymsg_updatedavatar(s,t)
                elif s[3] == Y_available:       #4
                    self.ymsg_back(s,t)
                elif s[3] == Y_calendar:
                    self.ymsg_notification(s,t)
                elif s[3] == Y_mail:            #11
                    self.ymsg_email(s,t)
                elif s[3] == Y_reqroom:         #150
                    self.ymsg_reqroom(s,t)
                #elif s[3] == Y_gotoroom:         #151
                #    self.ymsg_reqroom(s,t)
                elif s[3] == Y_joinroom:         #152
                    self.ymsg_joinroom(s,t)
                elif s[3] == Y_leaveroom:         #155
                    self.ymsg_leaveroom(s,t)
                elif s[3] == Y_chtmsg:         #168
                    self.ymsg_roommsg(s,t)
                elif s[3] == Y_init:            #76
                    self.ymsg_init()
                elif s[3] == Y_chatlogout:
                    self.chatlogin = False
                elif s[3] == Y_statusupdate15: #240
                    self.ymsg_statusupdate15(s, t)
                elif s[3] == Y_buddylist15:       #241
                    self.ymsg_buddylist15(s,t)
                else:
                    pass
                #print "remove packet"
                self.rbuf = self.rbuf[size:]

            else:
                break

if __name__ == '__main__':
    y = YahooCon('YID','password','jid','',True)
    while not y.connect():
        print 'sleep'
        time.sleep(5)

    print "connected ", y.sock
    y.sock.send(y.ymsg_send_challenge())

    while 1:
        y.Process()

