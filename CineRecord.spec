# -*- mode: python ; coding: utf-8 -*-

a = Analysis(['web/app.py'],
             pathex=['.'],
             datas=[
                 ('web/templates', 'templates'),
                 ('web/static', 'static')
             ],
             hiddenimports=[
                 'eventlet',
                 'eventlet.hubs.selects',
                 'eventlet.hubs.poll',
                 'eventlet.hubs.epolls',
                 'eventlet.hubs.kqueue',
                 'dns',
                 'dns.rdtypes.ANY',
                 'dns.rdtypes.IN',
                 'dns.rdtypes.CH',
                 'dns.rdtypes.dnskeybase',
                 'dns.asyncbackend',
                 'dns.dnssec',
                 'dns.e164'
             ],
             hookspath=[],
             runtime_hooks=[])
             
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='CineRecord',
          debug=False,
          strip=False,
          upx=False,
          console=True,
          icon='web/static/icon.icns')
