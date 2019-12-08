"""
QRZ cog for qrm
---
Copyright (C) 2019 Abigail Gold, 0x5c

This file is part of discord-qrmbot and is released under the terms of the GNU
General Public License, version 2.
"""
from collections import OrderedDict
from datetime import datetime
from io import BytesIO

import discord
from discord.ext import commands, tasks

import aiohttp
from lxml import etree

import common as cmn
import data.keys as keys


class QRZCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self._qrz_session_init.start()

    @commands.command(name="call", aliases=["qrz"], category=cmn.cat.lookup)
    async def _qrz_lookup(self, ctx: commands.Context, callsign: str):
        '''Look up a callsign on [QRZ.com](https://www.qrz.com/).'''
        if keys.qrz_user == '' or keys.qrz_pass == '':
            await ctx.send(f'http://qrz.com/db/{callsign}')
            return

        try:
            await qrz_test_session(self.key, self.session)
        except ConnectionError:
            await self.get_session()

        url = f'http://xmldata.qrz.com/xml/current/?s={self.key};callsign={callsign}'
        async with self.session.get(url) as resp:
            if resp.status != 200:
                raise ConnectionError(f'Unable to connect to QRZ (HTTP Error {resp.status})')
            resp_xml = etree.parse(BytesIO(await resp.read())).getroot()

        resp_xml_session = resp_xml.xpath('/x:QRZDatabase/x:Session',
                                          namespaces={'x': 'http://xmldata.qrz.com'})
        resp_session = {el.tag.split('}')[1]: el.text for el in resp_xml_session[0].getiterator()}
        if 'Error' in resp_session:
            if 'Session Timeout' in resp_session['Error']:
                await self.get_session()
                await self._qrz_lookup(ctx, callsign)
                return
            if 'Not found' in resp_session['Error']:
                embed = discord.Embed(title=f"QRZ Data for {callsign.upper()}",
                                      colour=cmn.colours.bad,
                                      description='No data found!',
                                      timestamp=datetime.utcnow())
                embed.set_footer(text=ctx.author.name,
                                 icon_url=str(ctx.author.avatar_url))
                await ctx.send(embed=embed)
                return
            raise ValueError(resp_session['Error'])

        resp_xml_data = resp_xml.xpath('/x:QRZDatabase/x:Callsign',
                                       namespaces={'x': 'http://xmldata.qrz.com'})
        resp_data = {el.tag.split('}')[1]: el.text for el in resp_xml_data[0].getiterator()}

        embed = discord.Embed(title=f"QRZ Data for {resp_data['call']}",
                              colour=cmn.colours.good,
                              url=f'http://www.qrz.com/db/{resp_data["call"]}',
                              timestamp=datetime.utcnow())
        embed.set_footer(text=ctx.author.name,
                         icon_url=str(ctx.author.avatar_url))
        if 'image' in resp_data:
            embed.set_thumbnail(url=resp_data['image'])

        data = qrz_process_info(resp_data)

        for title, val in data.items():
            if val is not None:
                embed.add_field(name=title, value=val, inline=True)
        await ctx.send(embed=embed)

    async def get_session(self):
        """Session creation and caching."""
        self.key = await qrz_login(keys.qrz_user, keys.qrz_pass, self.session)
        with open('data/qrz_session', 'w') as qrz_file:
            qrz_file.write(self.key)

    @tasks.loop(count=1)
    async def _qrz_session_init(self):
        """Helper task to allow obtaining a session at cog instantiation."""
        try:
            with open('data/qrz_session') as qrz_file:
                self.key = qrz_file.readline().strip()
            await qrz_test_session(self.key, self.session)
        except (FileNotFoundError, ConnectionError):
            await self.get_session()


async def qrz_login(user: str, passwd: str, session: aiohttp.ClientSession):
    url = f'http://xmldata.qrz.com/xml/current/?username={user};password={passwd};agent=qrmbot'
    async with session.get(url) as resp:
        if resp.status != 200:
            raise ConnectionError(f'Unable to connect to QRZ (HTTP Error {resp.status})')
        resp_xml = etree.parse(BytesIO(await resp.read())).getroot()

    resp_xml_session = resp_xml.xpath('/x:QRZDatabase/x:Session',
                                      namespaces={'x': 'http://xmldata.qrz.com'})
    resp_session = {el.tag.split('}')[1]: el.text for el in resp_xml_session[0].getiterator()}
    if 'Error' in resp_session:
        raise ConnectionError(resp_session['Error'])
    if resp_session['SubExp'] == 'non-subscriber':
        raise ConnectionError('Invalid QRZ Subscription')
    return resp_session['Key']


async def qrz_test_session(key: str, session: aiohttp.ClientSession):
    url = f'http://xmldata.qrz.com/xml/current/?s={key}'
    async with session.get(url) as resp:
        if resp.status != 200:
            raise ConnectionError(f'Unable to connect to QRZ (HTTP Error {resp.status})')
        resp_xml = etree.parse(BytesIO(await resp.read())).getroot()

    resp_xml_session = resp_xml.xpath('/x:QRZDatabase/x:Session',
                                      namespaces={'x': 'http://xmldata.qrz.com'})
    resp_session = {el.tag.split('}')[1]: el.text for el in resp_xml_session[0].getiterator()}
    if 'Error' in resp_session:
        raise ConnectionError(resp_session['Error'])


def qrz_process_info(data: dict):
    if 'name' in data:
        if 'fname' in data:
            name = data['fname'] + ' ' + data['name']
        else:
            name = data['name']
    else:
        name = None
    if 'state' in data:
        state = f', {data["state"]}'
    else:
        state = ''
    address = data.get('addr1', '') + '\n' + data.get('addr2', '') + \
        state + ' ' + data.get('zip', '')
    if 'eqsl' in data:
        eqsl = 'Yes' if data['eqsl'] == 1 else 'No'
    else:
        eqsl = 'Unknown'
    if 'mqsl' in data:
        mqsl = 'Yes' if data['mqsl'] == 1 else 'No'
    else:
        mqsl = 'Unknown'
    if 'lotw' in data:
        lotw = 'Yes' if data['lotw'] == 1 else 'No'
    else:
        lotw = 'Unknown'

    return OrderedDict([('Name', name),
                        ('Country', data.get('country', None)),
                        ('Address', address),
                        ('Grid Square', data.get('grid', None)),
                        ('County', data.get('county', None)),
                        ('CQ Zone', data.get('cqzone', None)),
                        ('ITU Zone', data.get('ituzone', None)),
                        ('IOTA Designator', data.get('iota', None)),
                        ('Expires', data.get('expdate', None)),
                        ('Aliases', data.get('aliases', None)),
                        ('Previous Callsign', data.get('p_call', None)),
                        ('License Class', data.get('class', None)),
                        ('eQSL?', eqsl),
                        ('Paper QSL?', mqsl),
                        ('LotW?', lotw),
                        ('QSL Info', data.get('qslmgr', None)),
                        ('CQ Zone', data.get('cqzone', None)),
                        ('ITU Zone', data.get('ituzone', None)),
                        ('IOTA Designator', data.get('iota', None)),
                        ('Born', data.get('born', None)),
                        ])


def setup(bot):
    bot.add_cog(QRZCog(bot))
