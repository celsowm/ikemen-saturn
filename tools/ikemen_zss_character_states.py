#!/usr/bin/env python3
"""Strict source-checked character-state lowering for KFM ZSS.

Only controllers already implemented by Ikemen Saturn are accepted.
Forty-six state bodies are translated, not merely their StateDef metadata.
Human throw recovery and strong-knee air follow-up are supported;
AI-random recovery is not yet modeled.
Other ZSS states keep the classic CNS fallback at runtime.

A source change invalidates the conversion until it has been reviewed
rather than silently introducing a behavior mismatch.
"""
from __future__ import annotations

import re
import hashlib
from pathlib import Path

from tools.ikemen_cns import (Section, State, _common_ctrl, parse_zss_states,
                              no_hit_by_attr_mask, no_hit_by_state_mask, q8, q16)

# Supported source bodies with every controller lowered in the exact order.
# Normalization discards insignificant spacing and ZSS '#' comments, but no
# executable token: any new controller causes a hard failure.
BODIES = {
    # Walk and run are the common1 locomotion bodies plus AI-only guards
    # (map(AIw) steering, the AI no-crouch/movement predicates). The human
    # path is byte-identical to the proven common1 lowering; AI behavior is
    # validated separately by tools/ikemen_zss_ai.py.
    20: ('ifcommand="holdback"&&!ailevelf||ailevelf&&map(aiw)=-1{'
         'velset{x:const(velocity.walk.back.x)}}'
         'elseifcommand="holdfwd"&&!ailevelf||ailevelf&&map(aiw)=1{'
         'velset{x:const(velocity.walk.fwd.x)}}'
         'ifvelx>0{ifcond(anim=5,animtime=0,anim!=20){changeanim{value:20}}}'
         'elseifvelx<0{ifcond(anim=5,animtime=0,anim!=21){changeanim{value:21}}}'),
    100: ('velset{x:const(velocity.run.fwd.x)}'
          'assertspecial{flag:nowalk;flag2:noautoturn}'
          'ifailevelf{assertspecial{flag:nocrouch}}'
          'ifcommand!="holdfwd"&&!ailevelf{changestate{value:0}}'),
    170: "nothitby{value:sca;time:1}",
    181: ("ifanimtime<-2{assertspecial{flag:roundnotover}}"
          "nothitby{value:sca;time:1}"),
    180: "changestate{value:181;ctrl:0}",
    # Pre-fight intro. The motif-only dialogue box has no gameplay effect and
    # is not lowered; its exact source text is pinned here so an edit fails.
    191: 'ifroundstate=0{changeanim{value:190}}assertspecial{flag:intro}persistent(0)ifroundstate!=0{explod{anim:191;postype:p1;pos:260,-90;velocity:-4.2,-7;accel:0,.32;removetime:48;}}ifanimelemtime(7)=1{explod{anim:192;postype:p1;pos:60,-70;velocity:2,-4;accel:0,.32;removetime:35;}}ifanimelem=7{callsyssnd(5,2,1);}ifanimelemtime(7)=3{callsyssnd(5,3,2);}ifenemy,name="kungfuman"{ifteamside=1{dialogue{text1:"<p1><p1face=self,9000,1><p2face=self,9000,1><p1faceactive=self,9003>hey...youlookjustlikeme!<wait=90>";text2:"<p2><p2faceactive=self,9003>ofcourseido...i\'mkungfumantoo!<wait=90>";text3:"<p1>thisisconfusing...<wait=60>\\nidon\'ttrustyou.<wait=90>";}}}ifanimtime=0{changestate{value:0}}',
    195: 'iftime=40{ctrlset{value:1}}callendstate(0);',
    200: ('ifanimelem=3{hitdef{attr:s,na;damage:23,0;animtype:light;guardflag:ma;'
          'hitflag:maf;priority:3,hit;pausetime:8,8;sparkno:0;sparkxy:-10,-76;'
          'hitsound:5,0;guardsound:6,0;ground.type:high;ground.slidetime:5;'
          'ground.hittime:11;ground.velocity:-4;airguard.velocity:-1.9,-.8;'
          'air.type:high;air.velocity:-1.4,-3;air.hittime:15;}}'
          'iftime=1{callcsnd(0,0,1);}callendstate(0);'),
    210: ('ifanimelemtime(2)>=0&&animelemtime(7)<0{width{value:15,0}}'
          'iftime=2{callcsnd(0,4,1);}ifanimelem=3{hitdef{attr:s,na;animtype:medium;'
          'damage:57;guardflag:ma;pausetime:12,12;sparkno:1;sparkxy:-10,-70;'
          'hitsound:5,2;guardsound:6,0;ground.type:high;ground.slidetime:12;'
          'ground.hittime:16;ground.velocity:-5.5;air.velocity:-2.5,-4;forcenofall:1;}}'
          'ignorehitpausepersistent(0)ifanimelemtime(5)>0&&animelemtime(6)<=0&&movecontact{'
          'changeanim{value:210;elem:6}}ifanimelem=5{sprpriority{value:2}}callendstate(0);'),
    230: ('iftime=2{callcsnd(0,0,1);}ifanimelem=3{hitdef{attr:s,na;'
          'animtype:medium;damage:26;guardflag:ma;pausetime:12,12;sparkno:0;'
          'sparkxy:-10,-37;hitsound:5,1;guardsound:6,0;ground.type:low;'
          'ground.slidetime:10;ground.hittime:14;ground.velocity:-5;'
          'air.velocity:-2.5,-3.5;}}callendstate(0);'),
    240: ('iftime=2{callcsnd(0,1,1);}ifanimelem=3{hitdef{attr:s,na;animtype:medium;'
          'damage:63;guardflag:ma;pausetime:12,12;sparkno:1;sparkxy:-10,-60;'
          'hitsound:5,2;guardsound:6,0;ground.type:low;ground.slidetime:12;'
          'ground.hittime:17;ground.velocity:-6;air.velocity:-2.2,-3.2;}}'
          'ifanimelem=7{posadd{x:12}}callendstate(0);'),
    400: ('iftime=1{callcsnd(0,0,1);}ifanimelem=2{hitdef{attr:c,na;damage:23;'
          'priority:3;animtype:light;hitflag:maf;guardflag:l;pausetime:10,11;'
          'sparkno:0;sparkxy:-10,-42;hitsound:5,0;guardsound:6,0;ground.type:low;'
          'ground.slidetime:4;ground.hittime:9;ground.velocity:-4;'
          'air.velocity:-1.5,-3;}}ifanimelemtime(3)=2{ctrlset{value:1}}callendstate(1);'),
    410: ('iftime=1{callcsnd(0,1,1);}ifanimelem=3{hitdef{attr:c,na;damage:37;'
          'animtype:medium;hitflag:maf;guardflag:m;pausetime:12,12;sparkno:1;'
          'sparkxy:-10,-55;hitsound:5,2;guardsound:6,0;ground.type:low;'
          'ground.slidetime:12;ground.hittime:17;ground.velocity:-4;air.velocity:-3,-4;}}'
          'ifanimelem=4{hitdef{attr:c,na;damage:36;animtype:medium;hitflag:maf;'
          'guardflag:ma;pausetime:12,12;sparkxy:-10,-83;hitsound:5,2;guardsound:6,0;'
          'ground.type:high;ground.slidetime:12;ground.hittime:17;ground.velocity:-7;'
          'air.velocity:-3,-4;}}callendstate(1);'),
    430: ('iftime=1{callcsnd(0,0,1);}ifanimelem=3{hitdef{attr:c,na;damage:28;'
          'animtype:light;hitflag:mafd;guardflag:l;pausetime:12,12;sparkno:0;'
          'sparkxy:-10,-8;hitsound:5,1;guardsound:6,0;ground.type:low;'
          'ground.slidetime:6;ground.hittime:10;ground.velocity:-5;'
          'air.velocity:-2,-3;down.velocity:-5,0;down.hittime:22;}}callendstate(1);'),
    440: ('iftime=1{callcsnd(0,2,1);}ifanimelem=4{hitdef{attr:c,na;damage:72;'
          'hitflag:mafd;guardflag:l;pausetime:12,12;sparkno:1;sparkxy:-5,-10;'
          'hitsound:5,2;guardsound:6,0;ground.type:trip;ground.slidetime:10;'
          'ground.hittime:17;ground.velocity:-1.5,-2;air.velocity:-1.2,-3;'
          'guard.velocity:-5;fall:1;}}callendstate(1);'),
    600: ('iftime=1{callcsnd(0,0,1);}ifanimelem=2{hitdef{attr:a,na;damage:20;'
          'guardflag:ha;priority:3;pausetime:7,8;sparkno:0;sparkxy:-10,-58;'
          'hitsound:5,0;guardsound:6,0;ground.type:high;ground.slidetime:5;'
          'ground.hittime:8;guard.ctrltime:8;ground.velocity:-4;air.velocity:-1.3,-3;'
          'air.hittime:14;}}ifanimelemtime(3)=2{ctrlset{value:1}}'),
    610: ('iftime=2{callcsnd(0,1,1);}ifanimelem=3{hitdef{attr:a,na;damage:72;'
          'guardflag:ha;priority:4;pausetime:12,12;sparkno:1;sparkxy:-10,-55;'
          'hitsound:5,3;guardsound:6,0;animtype:medium;ground.type:high;'
          'ground.slidetime:12;ground.hittime:14;guard.ctrltime:14;'
          'ground.velocity:-6;air.velocity:-3,-4;}}'),
    630: ('iftime=1{callcsnd(0,0,1);}ifanimelem=2{hitdef{attr:a,na;damage:26;'
          'guardflag:ha;priority:3;pausetime:8,8;sparkno:1;sparkxy:-5,-35;'
          'hitsound:5,0;guardsound:6,0;ground.type:high;ground.slidetime:6;'
          'ground.hittime:10;guard.ctrltime:10;ground.velocity:-4;'
          'air.velocity:-2,-3;air.hittime:14;}}'),
    640: ('iftime=2{callcsnd(0,1,1);}ifanimelem=2{hitdef{attr:a,na;damage:70;'
          'guardflag:ha;priority:4;pausetime:12,12;sparkno:1;sparkxy:-10,-40;'
          'hitsound:5,3;guardsound:6,0;animtype:medium;ground.type:high;'
          'ground.slidetime:12;ground.hittime:15;guard.ctrltime:15;'
          'ground.velocity:-7;air.velocity:-3,-4;}}'),
    # Throw attempt: Miss-priority HitDef at Time 0 moves the thrower to 810
    # and the victim to 820 on success; otherwise the whiff returns to idle.
    800: ('iftime=0{hitdef{attr:s,nt;hitflag:m-;priority:1,miss;sparkno:-1;'
          'p1sprpriority:1;p1facing:1;p2facing:1;p1stateno:810;p2stateno:820;'
          'guard.dist:0;fall:1;}}callendstate(0);'),
    # Blocking: guard-reversal stand/crouch/air startups, their pause-freeze
    # counter states and the landing state that re-enters blocking.
    1300: 'ifanimelemtime(3)<0{width{value:15,0}}iftime=0{callcsnd(0,1,1);reversaldef{reversal.attr:sa,aa;pausetime:0,0;sparkno:40;sparkxy:40,0;hitsound:6,0;p1stateno:1310;p1sprpriority:2;p2sprpriority:1;}hitoverride{attr:sa,ap;stateno:1310;time:8}}iftime=4&&command="holdfwd"||time=8{reversaldef{reversal.attr:}hitoverride{attr:;time:0}}callendstate(0);',
    1310: 'iftime=0{pause{time:20;endcmdbuftime:20;pausebg:0}nothitby{value:sca;time:1}}iftime=1&&command="holdback"{changestate{value:130;ctrl:1}}callendstate(0);',
    1320: 'ifanimelemtime(3)<0{width{value:10,0}}iftime=0{callcsnd(0,1,1);reversaldef{reversal.attr:c,aa;pausetime:0,0;sparkno:40;sparkxy:40,0;hitsound:6,0;p1stateno:1330;p1sprpriority:2;p2sprpriority:1;}}iftime=5{reversaldef{reversal.attr:}}iftime<5{hitoverride{attr:c,ap;stateno:1330}}callendstate(1);',
    1330: 'iftime=0{pause{time:20;endcmdbuftime:20;pausebg:0}nothitby{value:sca;time:1}}iftime=1&&command="holdback"{changestate{value:131;ctrl:1}}callendstate(1);',
    1340: 'ifanimelemtime(3)<0{width{value:10,0}}iftime=0{callcsnd(0,1,1);reversaldef{reversal.attr:a,aa;pausetime:0,0;sparkno:40;sparkxy:40,0;hitsound:6,0;p1stateno:1350;p1sprpriority:2;p2sprpriority:1;}}iftime=5{reversaldef{reversal.attr:}}iftime<5{hitoverride{attr:sa,ap;stateno:1350}}ifanimelem=4{ctrlset{value:1}}veladd{y:const(movement.yaccel)}ifposy>=0&&vely>0{changestate{value:1351}}',
    1350: 'iftime=0{pause{time:20;endcmdbuftime:20;pausebg:0}nothitby{value:sca;time:1}}iftime=1&&command="holdback"{changestate{value:132;ctrl:1}}ifanimelemtime(3)<0{posfreeze{}}ifanimelem=3{ctrlset{value:1}}ifanimelemtime(3)>0{veladd{y:const(movement.yaccel)}}ifposy>=0&&vely>0{changestate{value:1351}}',
    1351: 'iftime=0{velset{y:0}posset{y:0}}iftime=3{ctrlset{value:1}}ifcommand="blocking"{ifcommand!="holddown"{changestate{value:1300}}else{changestate{value:1320}}}callendstate(0);',
    # Hyper (super) moves: SuperPause freezes the world, then the combo body.
    3000: 'ifanimelem=2,>=0{width{value:15,0}}ifanimelem=2,1{superpause{pos:25,-57;anim:100;sound:20,0;poweradd:-1000;}afterimage{time:2}}ifanimelemtime(2)>=1&&animelemtime(25)<4{afterimagetime{time:2}}ifanimelem=2{nothitby{value:,na,sa,at;time:11}posadd{x:20}}ifanimelemtime(2)>=0&&animelemtime(14)<0{nothitby{value:c,na;time:1}}ifanimelem=4||animelem=12||animelem=20{callcsnd(0,3,1);}ifanimelem=3||animelem=11||animelem=13||animelem=19||animelem=21||animelem=31{posadd{x:10}}ifanimelem=5||animelem=13||animelem=21{velset{x:6}}ifanimelem=5{posadd{x:5}}ifanimelem=5||animelem=13{hitdef{attr:s,ha;animtype:hard;damage:72,4;getpower:0;priority:6;guardflag:ma;pausetime:15,15;sparkxy:-10,-60;hitsound:5,4;guardsound:6,0;ground.type:low;ground.slidetime:30;ground.hittime:32;ground.velocity:-6;air.velocity:-3,-2.8;air.fall:1;fall.animtype:hard;fall.recover:0;}}ifanimelem=21{hitdef{attr:s,ha;animtype:hard;damage:75,4;getpower:0;priority:5;guardflag:ma;pausetime:15,15;sparkxy:-10,-60;hitsound:5,4;guardsound:6,0;ground.type:low;ground.slidetime:30;ground.hittime:32;ground.velocity:-5,-4;guard.velocity:-12;air.velocity:-5,-4;airguard.velocity:-3,-3;fall.animtype:hard;fall:1;fall.recover:0;}}callendstate(0);',
    3050: 'ifanimelemtime(4)>=0&&animelemtime(16)<0{width{value:5,0}}ifanimelem=2{superpause{pos:-5,-55;anim:100;sound:20,0;poweradd:-1000}nothitby{value:,na,sa,at;time:6}}ifanimelemtime(2)>=0{afterimagetime{time:2}}ifanimelem=4{callcsnd(0,2,1);}iftime=0{hitdef{attr:s,ha;animtype:up;damage:155,12;getpower:0;priority:5;guardflag:ma;pausetime:30,30;sparkno:3;sparkxy:0,-110;hitsound:5,4;guardsound:6,0;ground.type:low;ground.slidetime:26;ground.hittime:28;ground.velocity:-1.3,-25;guard.velocity:-11;air.velocity:-1.3,-25;airguard.velocity:-4.5,-5;envshake.time:25;envshake.ampl:7;envshake.freq:176;p2facing:1;fall:1;fall.recover:0;fall.damage:70;fall.envshake.ampl:6;fall.envshake.freq:178;fall.envshake.time:15;mindist:50,-100;maxdist:100,-10;yaccel:.8;}}ifmovehit{changestate{value:3051}}callendstate(0);',
    3051: 'ifanimtime<-2{afterimagetime{time:2}}callendstate(0);[statedef-2][statedef-3]iftime=1&&(stateno=52||stateno=106){callcsnd(40,0,1);}',
    # Thrower side of the grab: bind the victim through the throw arc, then
    # hurt and release them into 821 at element 11.
    810: 'iftime=0{var(2):=command="holdfwd";}ifanimelem=2{callcsnd(1,1,1);}ifanimelem=7{callcsnd(800,0,1);}ifanimelemtime(2)<0{targetbind{pos:28,0}}ifanimelemtime(2)>=0&&animelemtime(12)<0{width{edge:60,0}ifanimelemtime(5)<0{targetbind{pos:58,0}}}ifanimelemtime(5)>=0&&animelemtime(6)<0{targetbind{pos:47,0}}ifvar(2)&&animelem=6{turn{}posadd{x:-37}targetfacing{value:-1}}ifanimelemtime(6)>=0&&animelemtime(7)<0{targetbind{pos:41,-60}}elseifanimelemtime(7)>=0&&animelemtime(8)<0{targetbind{pos:25,-75}}elseifanimelemtime(8)>=0&&animelemtime(9)<0{targetbind{pos:15,-90}}elseifanimelemtime(9)>=0&&animelemtime(10)<0{targetbind{pos:-5,-96}}elseifanimelemtime(10)>=0&&animelemtime(11)<0{targetbind{pos:-14,-90}}ifanimelem=11{targetbind{pos:-50,-50}targetlifeadd{value:-78}targetstate{value:821}}ifanimelem=12{turn{}}ifanimelem=15{posadd{x:-10}}callendstate(0);',
    1000: ('iftime=8{callcsnd(0,3,1);}ifanimelem=2{posadd{x:20}}'
           'ifanimelem=3||animelem=13{posadd{x:10}}ifanimelem=5{posadd{x:5}'
           'ifp2bodydistx<40{hitdef{attr:s,sa;animtype:hard;damage:90,4;priority:5;'
           'guardflag:ma;pausetime:15,15;sparkxy:-10,-60;hitsound:5,4;guardsound:6,0;'
           'ground.type:low;ground.slidetime:12;ground.hittime:17;ground.velocity:-4,-3.5;'
           'air.velocity:-4,-3;fall:1;}}else{hitdef{attr:s,sa;animtype:hard;damage:85,4;'
           'priority:4;guardflag:ma;pausetime:15,15;sparkxy:-10,-60;hitsound:5,4;'
           'guardsound:6,0;ground.type:low;ground.slidetime:12;ground.hittime:17;'
           'ground.velocity:-7;air.velocity:-4,-2.5;}}}ifanimelem=9{posadd{x:-5}}callendstate(0);'),
    1010: ('iftime=9{callcsnd(0,3,1);}ifanimelem=2{posadd{x:20}}'
           'ifanimelem=3||animelem=13{posadd{x:10}}ifanimelem=5{posadd{x:5}velset{x:4}'
           'ifp2bodydistx<40{hitdef{attr:s,sa;animtype:hard;damage:90,4;priority:5;'
           'guardflag:ma;pausetime:15,15;sparkxy:-10,-60;hitsound:5,4;guardsound:6,0;'
           'ground.type:low;ground.slidetime:12;ground.hittime:17;ground.velocity:-4,-3.5;'
           'air.velocity:-4,-3;fall:1;}}else{hitdef{attr:s,sa;animtype:hard;damage:85,4;'
           'priority:4;guardflag:ma;pausetime:15,15;sparkxy:-10,-60;hitsound:5,4;'
           'guardsound:6,0;ground.type:low;ground.slidetime:12;ground.hittime:17;'
           'ground.velocity:-7;air.velocity:-4,-2.5;}}}callendstate(0);'),
    1020: ('velmul{x:.85*ifelse(animelemtime(6)<0,1,.8)}iftime=0{'
           'afterimage{length:13;palbright:30,30,0;palcontrast:70,70,20;'
           'paladd:-10,-10,-10;palmul:.85,.85,.50;timegap:1;framegap:2;trans:add;time:2;}'
           'callexfx(20);}ifanimelemtime(8)<0{afterimagetime{time:2}}'
           'iftime=2{callcsnd(0,3,1);}ifanimelem=2{posadd{x:20}}'
           'ifanimelem=3||animelem=12{posadd{x:10}}ifanimelem=4{posadd{x:5}velset{x:13}'
           'hitdef{attr:s,sa;animtype:hard;damage:95,5;getpower:0;priority:4;guardflag:ma;'
           'pausetime:8,7;sparkxy:-10,-60;hitsound:5,4;guardsound:6,0;ground.type:low;'
           'ground.slidetime:20;ground.hittime:22;ground.velocity:-8,-7;guard.velocity:-7;'
           'air.velocity:-8,-7;airguard.velocity:-5,-4;fall:1;p2stateno:1025;p2facing:1;}}'
           'callendstate(0);'),
    1050: ('iftime=1{callcsnd(0,2,1);}ifanimelem=4{posadd{x:20}}'
           'ifanimelem=4{hitdef{attr:a,sa;animtype:medium;damage:80,4;priority:5;'
           'guardflag:ma;pausetime:12,12;sparkxy:-10,-70;hitsound:5,3;guardsound:6,0;'
           'ground.type:low;ground.slidetime:20;ground.hittime:22;ground.velocity:-3.5,-7;'
           'guard.velocity:-7;air.velocity:-3.5,-7;fall:1;}}ifanimtime=0{changestate{value:1051}}'),
    1060: ('iftime=1{callcsnd(0,2,1);}ifanimelem=2{posadd{x:6}}ifanimelem=4{posadd{x:21}}'
           'ifanimelem=4{hitdef{attr:a,sa;animtype:medium;damage:90,4;priority:5;'
           'guardflag:ma;pausetime:12,12;sparkxy:-10,-70;hitsound:5,3;guardsound:6,0;'
           'ground.type:low;ground.slidetime:20;ground.hittime:22;ground.velocity:-3.5,-7.5;'
           'guard.velocity:-7;air.velocity:-3.5,-7.5;fall:1;}}ifanimtime=0{changestate{value:1061}}'),
    1051: ('veladd{y:.45}'
           'if(command="a"||command="b")&&!ailevelf&&vely<-1{'
           'changestate{value:1055}}'
           'ifvely>0&&posy>=-10{changestate{value:1052}}'),
    1052: ('iftime=0{posset{y:0}callcsnd(40,0,1);}'
           'ifanimelem=3,-1{ctrlset{value:1}}'
           'ifanimelem=4{posadd{x:-15}}callendstate(0);'),
    1055: ('iftime=0{callcsnd(100,0,0);callcsnd(0,1,1);posadd{x:10;y:-10}}'
           'veladd{y:.45}ifanimelem=5{hitdef{attr:a,sa;animtype:medium;'
           'damage:35+(prevstateno=1061)*5,2;priority:4;guardflag:ma;'
           'pausetime:12,12;sparkxy:0,-90;hitsound:5,2;guardsound:6,0;'
           'ground.type:high;ground.slidetime:15;ground.hittime:18;'
           'ground.velocity:-6;guard.velocity:-8;guard.ctrltime:12;'
           'air.velocity:-4,-5;airguard.velocity:-4,-4.5;air.fall:1;}}'
           'ifvely>0&&posy>=-5{changestate{value:1056}}'),
    1056: 'iftime=0{posset{y:0}callcsnd(40,0,1);}callendstate(0);',
    1061: ('veladd{y:.45}'
           'if(command="a"||command="b")&&!ailevelf&&vely<-1{'
           'changestate{value:1055}}'
           'ifvely>0&&posy>=-10{changestate{value:1052}}'),
    820: ("iftime=0{changeanim2{value:820}}"
          "if!gethitvar(isbound){selfstate{value:5050}}"),
    1025: ("changeanim2{value:1025}"
           "ifhitshakeover=1{changestate{value:1026}}"),
    821: ('veladd{y:.4}'
          'ifvely>0&&alive&&canrecover&&(command="recovery"||random%5=0&&ailevelf){'
          'ifposy>=-20{changestate{value:5200}}'
          'else{selfstate{value:5210}}}'
          'ifposy>=0&&vely>0{selfstate{value:5100}}'),
    1026: ('iftime=0{hitvelset{x:1;y:1}}veladd{y:.45}'
           'ifposy<-15{'
           'ifbackedgebodydist<65||frontedgebodydist<65{'
           'screenbound{value:1;movecamera:0,1}}'
           'ifbackedgebodydist<=20||frontedgebodydist<=20{'
           'changestate{value:1027}}}'
           'ifvely>0&&posy>=0{selfstate{value:5100}}'),
    1028: ('nothitby{value:,na,np}iftime=0{'
           'velset{y:-6;x:1.6}ifbackedgedist<30{turn{}}'
           'if!selfanimexist(5052){changeanim{value:5050}}'
           'ifselfanimexist(5052){changeanim{value:5052}}}'
           'veladd{y:.35}ifvely>-2{'
           'persistent(0)ifanim=5050&&selfanimexist(5060){'
           'changeanim{value:5060}}'
           'persistent(0)ifanim=5052&&selfanimexist(5062){'
           'changeanim{value:5062}}}'
           'ifvely>0&&posy>=0{selfstate{value:5100}}'),
    1027: ('iftime=0{iffrontedgebodydist<=30{turn{}}'
           'posadd{x:15-backedgebodydist}'
           'explod{anim:f72;pos:0,floor(screenposy)-50;'
           'postype:back;sprpriority:3;}'
           'callsyssnd(7,0,1);changeanim2{value:1027}}'
           'posfreeze{}screenbound{value:1;movecamera:0,1}'
           'ifanimtime=0{changestate{value:1028}}'),
}

# These long bodies are checked in full after whitespace/comment normalization.
BODY_SHA256 = {
    1100: '69b426553c976f1c9c9f96930b3b595d4b2406d2b4ed0ae23dc1c5edd60d3e42',
    1110: '534580b0dd41602e5a9059f22633fc9548d666e107506a780c50f68dee902123',
    1120: 'acb0e7406817aed684e9569f093bf3b6c5254d34c88954de44caaefc9f442664',
    1200: 'b038e40cc37723fa045df95bd6ffe87ac45b60c965b24105f9ba53268079e9b5',
    1210: '6e563819eeff99ed614fc5f40595ec99178addc4132eafb3eb2f09ab43c69a90',
    1220: 'fc94aa7fba833d76a12fc7d5eb67295b4fa31217127b5dfc346f8d135a53482e',
    1400: '4619c48408e02186bc9b965106dd8b0cdbe495c85759647fe55bcc13116a40ea',
    1410: '167db298085eccfd89e180f0ffc053ae25e896563073ee4bdc4106f1e919c212',
    1420: '6238893929af3666df9a3299185cec80f1d2510fab0c2550098eba4666a2d4fb',
    1070: '945ef8a0ed2b9ad341a3230b3187080e476a4d274d633bc34348d400098dbaae',
    1071: '1328d2942ffac387a7258ad44a458775cf4f862b524377aa9f981f668139fce3',
    1075: 'deacb575b31defd5fd88bca4b0f19eaa3180ea9ef6cacc66fe6b095f7c8fce48',
}
CHARACTER_STATES = (20, 100, 170, 180, 181, 191, 195, 200, 800, 810, 3000, 3050, 3051, 1300, 1310, 1320, 1330, 1340, 1350, 1351, 210, 230, 240, 400, 410, 430, 440, 600, 610, 630, 640, 1000, 1010, 1020, 1050, 1051, 1052, 1055, 1056, 1060, 1061, 1070, 1071, 1075, 1100, 1110, 1120, 1200, 1210, 1220, 1400, 1410, 1420)
HIT_STATES = (820, 821, 1025, 1026, 1027, 1028)

# These guards protect against silently compiling outdated states with an
# incompatible move class, physics type or action.
METADATA = {
    20: {"type": "S", "physics": "S", "sprpriority": "0"},
    100: {"type": "S", "physics": "S", "anim": "100", "sprpriority": "1"},
    170: {"type": "S", "movetype": "I", "physics": "S", "anim": "170", "ctrl": "0"},
    181: {"type": "S", "movetype": "I", "physics": "S", "anim": "181",
          "ctrl": "0", "velset": "0,0", "sprpriority": "1"},
    180: {"type": "S", "movetype": "I", "physics": "S", "anim": "-2", "ctrl": "0"},
    191: {"type": "S", "movetype": "I", "physics": "S", "anim": "190", "ctrl": "0", "velset": "0,0", "sprpriority": "1"},
    195: {"type": "S", "movetype": "I", "physics": "S", "anim": "195", "ctrl": "0", "velset": "0,0", "sprpriority": "2"},
    800: {"type": "S", "movetype": "A", "physics": "S", "anim": "800",
          "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "0"},
    1300: {"type": "S", "movetype": "I", "physics": "S", "anim": "1300", "ctrl": "0", "velset": "0,0", "sprpriority": "1"},
    1310: {"type": "S", "movetype": "I", "physics": "S", "anim": "1310", "ctrl": "0", "velset": "0,0", "sprpriority": "2"},
    1320: {"type": "C", "movetype": "I", "physics": "C", "anim": "1320", "ctrl": "0", "velset": "0,0", "sprpriority": "1"},
    1330: {"type": "C", "movetype": "I", "physics": "C", "anim": "1330", "ctrl": "0", "velset": "0,0", "sprpriority": "2"},
    1340: {"type": "A", "movetype": "I", "physics": "N", "anim": "1340", "ctrl": "0", "sprpriority": "1"},
    1350: {"type": "A", "movetype": "I", "physics": "N", "anim": "1350", "ctrl": "0", "sprpriority": "2"},
    1351: {"type": "S", "physics": "S", "anim": "47", "ctrl": "0"},
    3000: {"type": "S", "movetype": "A", "physics": "S", "anim": "3000", "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "4"},
    3050: {"type": "S", "movetype": "A", "physics": "S", "anim": "3050", "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "4"},
    3051: {"type": "S", "movetype": "A", "physics": "S", "anim": "3051"},
    810: {"type": "S", "movetype": "A", "physics": "N", "anim": "810", "poweradd": "0"},
    200: {"type": "S", "movetype": "A", "physics": "S", "anim": "200",
          "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "1", "poweradd": "10"},
    210: {"type": "S", "movetype": "A", "physics": "S", "anim": "210",
          "ctrl": "0", "velset": "0,0", "sprpriority": "-1", "juggle": "4", "poweradd": "30"},
    230: {"type": "S", "movetype": "A", "physics": "S", "anim": "230",
          "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "4", "poweradd": "11"},
    240: {"type": "S", "movetype": "A", "physics": "S", "anim": "240",
          "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "5", "poweradd": "30"},
    400: {"type": "C", "movetype": "A", "physics": "C", "anim": "400",
          "ctrl": "0", "sprpriority": "2", "juggle": "5", "poweradd": "8"},
    410: {"type": "C", "movetype": "A", "physics": "C", "anim": "410",
          "ctrl": "0", "sprpriority": "2", "juggle": "6", "poweradd": "25"},
    430: {"type": "C", "movetype": "A", "physics": "C", "anim": "430",
          "ctrl": "0", "sprpriority": "2", "juggle": "5", "poweradd": "11"},
    440: {"type": "C", "movetype": "A", "physics": "C", "anim": "440",
          "ctrl": "0", "sprpriority": "2", "juggle": "7", "poweradd": "35"},
    **{n: {"type": "A", "movetype": "A", "physics": "A", "anim": str(n),
           "ctrl": "0", "sprpriority": "2", "juggle": str(juggle), "poweradd": str(power)}
       for n, juggle, power in ((600, 2, 5), (610, 4, 30), (630, 3, 10), (640, 4, 30))},
    **{n: {"type": "S", "movetype": "A", "physics": "S", "anim": str(n),
           "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "4", "poweradd": str(power)}
       for n, power in ((1000, 55), (1010, 60), (1050, 55), (1060, 60))},
    1020: {"type": "S", "movetype": "A", "physics": "N", "anim": "1020",
           "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "6", "poweradd": "-330"},
    **{n: {"type": "S", "movetype": "A", "physics": "S", "anim": str(n),
           "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "4", "poweradd": str(power)}
       for n, power in ((1100, 55), (1110, 60), (1200, 50), (1210, 60))},
    **{n: {"type": "S", "movetype": "A", "physics": "S", "anim": str(n),
           "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "6", "poweradd": "-330"}
       for n in (1120, 1220)},
    **{n: {"type": "S", "movetype": "A", "physics": "N", "anim": str(n),
           "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": str(juggle), "poweradd": str(power)}
       for n, juggle, power in ((1400, 4, 50), (1410, 4, 50), (1420, 6, -330))},
    1051: {"type": "A", "movetype": "A", "physics": "N",
           "velset": "2,-6", "anim": "1051", "hitdefpersist": "1"},
    1052: {"type": "S", "movetype": "I", "physics": "S", "anim": "1052",
           "sprpriority": "1", "velset": "0,0"},
    1055: {"type": "A", "movetype": "A", "physics": "N", "anim": "1055"},
    1056: {"type": "S", "movetype": "I", "physics": "S", "anim": "1056",
           "sprpriority": "1", "velset": "0,0"},
    1070: {"type": "S", "movetype": "A", "physics": "S", "anim": "1070",
           "ctrl": "0", "velset": "0,0", "sprpriority": "2", "juggle": "6", "poweradd": "-330"},
    1071: {"type": "A", "movetype": "A", "physics": "N", "anim": "1071", "velset": "2.5,-9"},
    1075: {"type": "A", "movetype": "A", "physics": "N", "anim": "1055"},
    1061: {"type": "A", "movetype": "A", "physics": "N",
           "velset": "2,-7.5", "anim": "1051", "hitdefpersist": "1"},
    820: {"type": "A", "movetype": "H", "physics": "N", "velset": "0,0"},
    1025: {"type": "A", "movetype": "H", "physics": "N", "velset": "0,0"},
    821: {"type": "A", "movetype": "H", "physics": "N",
          "velset": "2.8,-7", "poweradd": "40"},
    1026: {"type": "A", "movetype": "H", "physics": "N"},
    1028: {"type": "A", "movetype": "H", "physics": "N"},
    1027: {"type": "A", "movetype": "H", "physics": "N"},
}


def normalize_body(source: str) -> str:
    # These selected states contain no quoted # characters.
    lines = [line.split("#", 1)[0] for line in source.splitlines()]
    return re.sub(r"\s+", "", "".join(lines)).lower()


def zss_row_patch(state: int) -> dict:
    """State-row fields the source StateDef omits but the runtime needs.

    Only the shared, verified locomotion lowering supplies these; every other
    state keeps exactly the row its own StateDef produces.
    """
    if state in (20, 100):
        from tools.ikemen_cns import locomotion_row_patch
        return locomotion_row_patch(state)
    return {}


def _controllers(state: int, const: dict[str, int] | None = None) -> list[dict]:
    if state in (20, 100):
        if const is None:
            raise ValueError(
                f"state {state}: locomotion lowering requires the resolved "
                "velocity constants")
        from tools.ikemen_cns import locomotion_ctrl_rows
        return locomotion_ctrl_rows(state, const)
    if state == 170:
        # Invulnerable to S/C/A attackers for one tick (refreshed each tick).
        return [_common_ctrl(
            170, "IK_CNS_CTRL_NOT_HIT_BY",
            "IK_CNS_TRIGGER_ALWAYS", 0, 0, 7, 1)]
    if state == 180:
        return [_common_ctrl(
            180, "IK_CNS_CTRL_CHANGE_STATE",
            "IK_CNS_TRIGGER_ALWAYS", 0, 0, 181, 0,
            "IK_CNS_CTRL_HAS_CTRL")]
    if state == 181:
        # Win pose: keep the round fadeout held and stay unhittable while
        # the pose animation still has 3+ ticks to run ("AnimTime < -2").
        return [
            _common_ctrl(
                181, "IK_CNS_CTRL_ASSERT_ROUND_NOT_OVER",
                "IK_CNS_TRIGGER_ANIM_TIME_REMAIN_GT", 2, 0, 1),
            _common_ctrl(
                181, "IK_CNS_CTRL_NOT_HIT_BY",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 7, 1),
        ]
    if state == 195:
        return [
            _common_ctrl(195, "IK_CNS_CTRL_CTRL_SET", "IK_CNS_TRIGGER_TIME_EQ", 40, 0, 1),
            _common_ctrl(195, "IK_CNS_CTRL_CHANGE_STATE", "IK_CNS_TRIGGER_ANIM_END", 0, 0, 0, 0,
                         "IK_CNS_CTRL_HAS_CTRL | IK_CNS_CTRL_CTRL_FROM_ROUND"),
        ]
    if state in (1052, 1056):
        return [
            _common_ctrl(state, "IK_CNS_CTRL_POS_SET", "IK_CNS_TRIGGER_TIME_EQ",
                         0, 0, 0, 0, "IK_CNS_CTRL_AXIS_Y"),
            _common_ctrl(state, "IK_CNS_CTRL_SOUND_EVENT", "IK_CNS_TRIGGER_TIME_EQ",
                         0, 0, 40, 0),
            *([_common_ctrl(1052, "IK_CNS_CTRL_CTRL_SET",
                            "IK_CNS_TRIGGER_ANIM_ELEM_TIME_EQ_PACKED", (3 << 8) | 255, 0, 1),
               _common_ctrl(1052, "IK_CNS_CTRL_POS_ADD", "IK_CNS_TRIGGER_ANIM_ELEM_EQ",
                            4, 0, q8(-15))] if state == 1052 else []),
            _common_ctrl(state, "IK_CNS_CTRL_CHANGE_STATE", "IK_CNS_TRIGGER_ANIM_END",
                         0, 0, 0, 0,
                         "IK_CNS_CTRL_HAS_CTRL | IK_CNS_CTRL_CTRL_FROM_ROUND"),
        ]
    if state in (1051, 1061):
        # Both knees keep the previous HitDef while jumping, allow human
        # a/b air-kick follow-up on ascent, then land at Pos Y >= -10.
        return [
            _common_ctrl(
                state, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.45),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.45)),
            _common_ctrl(
                state, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_COMMAND_ANY_VY_LT_Q8",
                (1 << 5) | (1 << 6), q8(-1), 1055),
            _common_ctrl(
                state, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_LEVEL", q8(-10), 0, 1052),
        ]
    if state == 820:
        return [
            _common_ctrl(
                820, "IK_CNS_CTRL_CHANGE_ANIM2",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 820),
            _common_ctrl(
                820, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_NOT_BOUND", 0, 0, 5050),
        ]
    if state == 1025:
        return [
            _common_ctrl(
                1025, "IK_CNS_CTRL_CHANGE_ANIM2",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 1025),
            _common_ctrl(
                1025, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_HIT_SHAKE_OVER", 0, 0, 1026),
        ]
    if state == 821:
        # Source chooses ground recovery first (Pos Y >= -20), then airborne
        # recovery, then ground collision. Random AI recovery remains deferred.
        return [
            _common_ctrl(
                821, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.4),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.4)),
            _common_ctrl(
                821, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_THROW_GROUND_RECOVERY", q8(-20),
                0, 5200),
            _common_ctrl(
                821, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_THROW_AIR_RECOVERY", 0, 0, 5210),
            _common_ctrl(
                821, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0, 5100),
        ]
    if state == 1026:
        return [
            _common_ctrl(
                1026, "IK_CNS_CTRL_HIT_VEL_SET",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 0, 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y"),
            _common_ctrl(
                1026, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.45),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.45)),
            _common_ctrl(
                1026, "IK_CNS_CTRL_SCREEN_BOUND",
                "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE_LT", q8(-15),
                65, 1, 0, value2=1, value3=3),
            _common_ctrl(
                1026, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_AIR_NEAR_BODY_EDGE", q8(-15),
                20, 1027),
            _common_ctrl(
                1026, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0, 5100),
        ]
    if state == 1027:
        # Script order matters: turn first, compute the new back-body
        # distance for PosAdd (not the pre-turn context), then F72 and
        # common-system SND (7,0). Screen Y is fixed in the Saturn stage.
        return [
            _common_ctrl(
                1027, "IK_CNS_CTRL_TURN",
                "IK_CNS_TRIGGER_STATE_ENTRY_FRONT_EDGE_BODY_LE", 30),
            _common_ctrl(
                1027, "IK_CNS_CTRL_POS_ADD_FROM_BACK_EDGE",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, q8(15), 1),
            _common_ctrl(
                1027, "IK_CNS_CTRL_SCREEN_BACK_EFFECT",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 72, -50),
            _common_ctrl(
                1027, "IK_CNS_CTRL_SOUND_EVENT",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 7, 0),
            _common_ctrl(
                1027, "IK_CNS_CTRL_CHANGE_ANIM2",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 1027),
            _common_ctrl(
                1027, "IK_CNS_CTRL_POS_FREEZE",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, 0,
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y"),
            _common_ctrl(
                1027, "IK_CNS_CTRL_SCREEN_BOUND",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 1, 0,
                value2=1, value3=3),
            _common_ctrl(
                1027, "IK_CNS_CTRL_CHANGE_STATE",
                "IK_CNS_TRIGGER_ANIM_END", 0, 0, 1028),
        ]
    if state == 1028:
        # NA/NP immunity, 1.6/-6 bounce, back-edge turn, native AIR
        # selection and persistent-once descending animations 5050->5060
        # / 5052->5062. No new game-specific controller type required.
        raw = ", NA, NP"
        mask = (f"({no_hit_by_state_mask(raw)}) | "
                f"(({no_hit_by_attr_mask(raw)}) << 8)")
        return [
            _common_ctrl(
                1028, "IK_CNS_CTRL_NOT_HIT_BY",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, mask, 1),
            _common_ctrl(
                1028, "IK_CNS_CTRL_VEL_SET",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0,
                q8(1.6), q8(-6),
                "IK_CNS_CTRL_AXIS_X | IK_CNS_CTRL_AXIS_Y | IK_CNS_CTRL_LOCAL_X",
                value4=q16(1.6), value5=q16(-6)),
            _common_ctrl(
                1028, "IK_CNS_CTRL_TURN",
                "IK_CNS_TRIGGER_STATE_ENTRY_BACK_EDGE_LT", 30),
            _common_ctrl(
                1028, "IK_CNS_CTRL_CHANGE_ANIM_IF_EXISTS",
                "IK_CNS_TRIGGER_TIME_EQ", 0, 0, 5052, 5050),
            _common_ctrl(
                1028, "IK_CNS_CTRL_VEL_ADD",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, 0, q8(0.35),
                "IK_CNS_CTRL_AXIS_Y", value5=q16(0.35)),
            _common_ctrl(
                1028, "IK_CNS_CTRL_CHANGE_ANIM_DESCENT_IF_EXISTS",
                "IK_CNS_TRIGGER_ALWAYS", 0, 0, q8(-2), 5050,
                value2=10, value3=1),
            _common_ctrl(
                1028, "IK_CNS_CTRL_SELF_STATE",
                "IK_CNS_TRIGGER_VY_GT_Q8_AT_FLOOR", 0, 0, 5100),
        ]
    raise ValueError(f"no native ZSS lowering for state {state}")


def compile_zss_overrides(
    character_zss: Path, hits_zss: Path, const: dict[str, int],
) -> dict[int, tuple[State, list[dict]]]:
    results = {}
    # State 195 calls this shared source function; fail closed on changes to it.
    function_source = character_zss.read_text()
    function_match = re.search(
        r'\[\s*Function\s+EndState\s*\(\s*type\s*\)\s*\]'
        r'(.*?)(?=\[\s*(?:Function|StateDef)\b|\Z)',
        function_source, flags=re.IGNORECASE | re.DOTALL)
    if not function_match or normalize_body(function_match.group(1)) != (
            'ifanimtime=0{changestate{value:11*$type;ctrl:roundstate>1}}'):
        raise ValueError(f"{character_zss}: EndState function changed")
    sound_match = re.search(
        r'\[\s*Function\s+CSnd\s*\(\s*bank\s*,\s*sound\s*,\s*c\s*\)\s*\]'
        r'(.*?)(?=\[\s*(?:Function|StateDef)\b|\Z)',
        function_source, flags=re.IGNORECASE | re.DOTALL)
    if not sound_match or normalize_body(sound_match.group(1)) != (
            'playsnd{value:s$bank,$sound;channel:$c}'):
        raise ValueError(f"{character_zss}: CSnd function changed")
    syssnd_match = re.search(
        r'\[\s*Function\s+SysSnd\s*\(\s*b\s*,\s*s\s*,\s*c\s*\)\s*\]'
        r'(.*?)(?=\[\s*(?:Function|StateDef)\b|\Z)',
        function_source, flags=re.IGNORECASE | re.DOTALL)
    if not syssnd_match or normalize_body(syssnd_match.group(1)) != (
            'playsnd{value:f$b,$s;channel:$c}'):
        raise ValueError(f"{character_zss}: SysSnd function changed")
    exfx_match = re.search(
        r'\[\s*Function\s+EXFX\s*\(\s*time\s*\)\s*\]'
        r'(.*?)(?=\[\s*(?:Function|StateDef)\b|\Z)',
        function_source, flags=re.IGNORECASE | re.DOTALL)
    if not exfx_match or normalize_body(exfx_match.group(1)) != (
            'palfx{time:$time;add:32,16,0;sinadd:64,32,5,3}'):
        raise ValueError(f"{character_zss}: EXFX function changed")
    for path, selected in (
        (character_zss, CHARACTER_STATES),
        (hits_zss, HIT_STATES),
    ):
        source = parse_zss_states(path)
        for number in selected:
            item = source.get(number)
            if item is None:
                raise ValueError(f"{path}: missing ZSS StateDef {number}")
            observed = normalize_body(item.body)
            if (hashlib.sha256(observed.encode()).hexdigest() != BODY_SHA256[number]
                    if number in BODY_SHA256 else observed != BODIES[number]):
                raise ValueError(
                    f"{path}: ZSS state {number} body changed or has "
                    "unsupported controllers; refusing partial conversion")
            for key, value in METADATA[number].items():
                actual = re.sub(r"\s+", "", item.metadata.get(key, "")).upper()
                if actual != value.upper():
                    raise ValueError(
                        f"{path}: state {number} {key} changed: "
                        f"{actual!r} != {value!r}")
            # The generic CNS compiler handles native StateDef metadata and
            # C emission. Controller bytecode comes only from verified ZSS.
            sd = Section(f"Statedef {number}", list(item.metadata.items()))
            if number in (1070, 1071, 1075):
                hit_body = observed.split('hitdef{', 1)[1].split('}', 1)[0]
                hit_fields = [tuple(part.split(':', 1)) for part in hit_body.split(';') if part]
                sections = []
                if number in (1070, 1075):
                    sections.append(Section(f'State {number} trail', [('type', 'AfterImageTime'), ('trigger1', '1'), ('time', '2')]))
                if number == 1070:
                    after_body = observed.split('afterimage{', 1)[1].split('}', 1)[0]
                    after_fields = [tuple(part.split(':', 1)) for part in after_body.split(';') if part]
                    sections.append(Section('State 1070 afterimage', [('type', 'AfterImage'), ('trigger1', 'Time = 0')] + after_fields))
                sections.append(Section(f'State {number} palfx', [('type', 'PalFX'), ('trigger1', 'Time = 0'), ('time', '20' if number == 1070 else '18'), ('add', '32,16,0'), ('sinadd', '64,32,5,3')]))
                if number == 1070:
                    sections.extend([
                        Section('State 1070 sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 1'), ('value', '0,2')]),
                        Section('State 1070 step 2', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 2'), ('x', '6')]),
                        Section('State 1070 step 4', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 4'), ('x', '21')]),
                    ])
                if number == 1071:
                    sections.append(Section('State 1071 trail', [('type', 'AfterImageTime'), ('trigger1', 'Vel Y < 0'), ('time', '2')]))
                if number == 1075:
                    sections.extend([
                        Section('State 1075 voice', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '100,0')]),
                        Section('State 1075 sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '0,1')]),
                        Section('State 1075 offset', [('type', 'PosAdd'), ('trigger1', 'Time = 0'), ('x', '10'), ('y', '-10')]),
                    ])
                sections.append(Section(f'State {number} hit', [('type', 'HitDef'), ('trigger1', 'AnimElem = 4' if number == 1070 else 'Time = 0')] + hit_fields))
                if number != 1070:
                    sections.extend([
                        Section(f'State {number} gravity', [('type', 'VelAdd'), ('trigger1', '1'), ('y', '.5')]),
                        Section(f'State {number} extra gravity', [('type', 'VelAdd'), ('trigger1', 'Vel Y >= -1'), ('y', '.2')]),
                    ])
                if number == 1071:
                    sections.append(Section('State 1071 cancel', [('type', 'ChangeState'), ('trigger1', 'Command = "a" || Command = "b"'), ('trigger1', 'Vel Y < -1'), ('trigger1', 'Time > 0'), ('value', '1075')]))
                sections.append(Section(f'State {number} end', [('type', 'ChangeState'),
                    ('trigger1', 'AnimTime = 0' if number == 1070 else 'Vel Y > 0 && Pos Y >= -10' if number == 1071 else 'Vel Y > 0 && Pos Y >= -5'),
                    ('value', '1071' if number == 1070 else '1052' if number == 1071 else '1056')]))
                results[number] = (State(number, sd, sections), [])
            elif number in (1400, 1410, 1420):
                hits = re.findall(r'hitdef\{([^}]*)\}', observed)
                if len(hits) != (2 if number == 1420 else 1):
                    raise ValueError(f"state {number}: unexpected HitDef count")
                sections = []
                if number == 1420:
                    after_body = observed.split('afterimage{', 1)[1].split('}', 1)[0]
                    after_fields = [tuple(part.split(':', 1)) for part in after_body.split(';') if part]
                    sections.extend([
                        Section('State 1420 afterimage', [('type', 'AfterImage'), ('trigger1', 'Time = 0')] + after_fields),
                        Section('State 1420 palfx', [('type', 'PalFX'), ('trigger1', 'Time = 0'), ('time', '20'), ('add', '32,16,0'), ('sinadd', '64,32,5,3')]),
                        Section('State 1420 trail', [('type', 'AfterImageTime'), ('trigger1', 'AnimElemTime(8) < 0'), ('time', '2')]),
                    ])
                sections.extend([
                    Section(f'State {number} sound', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 3'), ('value', '0,3')]),
                    Section(f'State {number} friction', [('type', 'VelMul'), ('trigger1', '1'), ('x', {1400: '.5', 1410: '.65', 1420: '.7'}[number])]),
                ])
                for index, hit in enumerate(hits):
                    fields = [tuple(part.split(':', 1)) for part in hit.split(';') if part]
                    trigger = ('Time = 0' if number != 1420 else
                               'AnimElemTime(4) = -2' if index == 0 else 'AnimElem = 4')
                    sections.append(Section(f'State {number} hit {index}', [('type', 'HitDef'), ('trigger1', trigger)] + fields))
                steps = (2, 3, 4, {1400: 8, 1410: 9, 1420: 10}[number])
                sections.append(Section(f'State {number} steps', [('type', 'PosAdd')] +
                                        [(f'trigger{i+1}', f'AnimElem = {e}') for i, e in enumerate(steps)] + [('x', '10')]))
                sections.append(Section(f'State {number} velocity', [('type', 'VelSet'),
                    ('trigger1', 'AnimElemTime(3) = [1, 2]' if number == 1420 else 'AnimElem = 4'),
                    ('x', {1400: '2', 1410: '8', 1420: '20'}[number])]))
                sections.append(Section(f'State {number} end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]))
                results[number] = (State(number, sd, sections), [])
            elif number in (1120, 1220):
                upper = number == 1120
                hits = re.findall(r'hitdef\{([^}]*)\}', observed)
                if len(hits) != (2 if upper else 1):
                    raise ValueError(f"state {number}: unexpected HitDef count")
                after_body = observed.split('afterimage{', 1)[1].split('}', 1)[0]
                after_fields = [tuple(part.split(':', 1)) for part in after_body.split(';') if part]
                sections = []
                if upper:
                    sections.append(Section('State 1120 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(4) >= 0 && AnimElemTime(14) < 0'), ('value', '5,0')]))
                    sections.append(Section('State 1120 sound', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 4'), ('value', '0,2')]))
                sections.extend([
                    Section(f'State {number} afterimage', [('type', 'AfterImage'), ('trigger1', 'Time = 0')] + after_fields),
                    Section(f'State {number} palfx', [('type', 'PalFX'), ('trigger1', 'Time = 0'), ('time', '20'), ('add', '32,16,0'), ('sinadd', '64,32,5,3')]),
                    Section(f'State {number} trail', [('type', 'AfterImageTime'), ('trigger1', 'AnimTime < -2'), ('time', '2')]),
                ])
                if not upper:
                    sections.extend([
                        Section('State 1220 sound', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 4'), ('value', '0,3')]),
                        Section('State 1220 width 5', [('type', 'Width'), ('trigger1', 'AnimElemTime(5) >= 0 && AnimElemTime(6) < 0'), ('value', '10,0')]),
                        Section('State 1220 width 6', [('type', 'Width'), ('trigger1', 'AnimElemTime(6) >= 0 && AnimElemTime(9) < 0'), ('value', '20,0')]),
                        Section('State 1220 shake', [('type', 'EnvShake'), ('trigger1', 'AnimElem = 6'), ('time', '8'), ('ampl', '3'), ('freq', '170')]),
                    ])
                for index, hit in enumerate(hits):
                    fields = [tuple(part.split(':', 1)) for part in hit.split(';') if part]
                    triggers = [('trigger1', 'Time = 0' if index == 0 else 'AnimElem = 7')]
                    if upper and index == 0:
                        triggers.append(('trigger2', 'AnimElem = 4'))
                    sections.append(Section(f'State {number} hit {index}', [('type', 'HitDef')] + triggers + fields))
                sections.append(Section(f'State {number} end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]))
                results[number] = (State(number, sd, sections), [])
            elif number in (1100, 1110, 1200, 1210):
                hits = re.findall(r'hitdef\{([^}]*)\}', observed)
                upper = number in (1100, 1110)
                if len(hits) != (2 if upper else 1):
                    raise ValueError(f"state {number}: unexpected HitDef count")
                sections = []
                if upper:
                    end_elem = 13 if number == 1100 else 14
                    sections.append(Section(f'State {number} width', [('type', 'Width'), ('trigger1', f'AnimElemTime(4) >= 0 && AnimElemTime({end_elem}) < 0'), ('value', '5,0')]))
                else:
                    sections.extend([
                        Section(f'State {number} width 5', [('type', 'Width'), ('trigger1', 'AnimElemTime(5) >= 0 && AnimElemTime(6) < 0'), ('value', '10,0')]),
                        Section(f'State {number} width 6', [('type', 'Width'), ('trigger1', 'AnimElemTime(6) >= 0 && AnimElemTime(9) < 0'), ('value', '20,0')]),
                        Section(f'State {number} shake', [('type', 'EnvShake'), ('trigger1', 'AnimElem = 6'), ('time', '4' if number == 1200 else '8'), ('ampl', '2'), ('freq', '180' if number == 1200 else '170')]),
                    ])
                sections.append(Section(f'State {number} sound', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 4'), ('value', '0,2' if upper else '0,3')]))
                for index, hit in enumerate(hits):
                    fields = [tuple(part.split(':', 1)) for part in hit.split(';') if part]
                    sections.append(Section(f'State {number} hit {index}', [('type', 'HitDef'), ('trigger1', 'Time = 0' if index == 0 else 'AnimElem = 7')] + fields))
                sections.append(Section(f'State {number} end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]))
                results[number] = (State(number, sd, sections), [])
            elif number == 1020:
                hit_body = observed.split('hitdef{', 1)[1].split('}', 1)[0]
                hit_fields = [tuple(part.split(':', 1)) for part in hit_body.split(';') if part]
                after_body = observed.split('afterimage{', 1)[1].split('}', 1)[0]
                after_fields = [tuple(part.split(':', 1)) for part in after_body.split(';') if part]
                sections = [
                    Section('State 1020 friction', [('type', 'VelMul'), ('trigger1', '1'), ('x', '.85 * ifelse(AnimElemTime(6) < 0, 1, .8)')]),
                    Section('State 1020 afterimage', [('type', 'AfterImage'), ('trigger1', 'Time = 0')] + after_fields),
                    Section('State 1020 palfx', [('type', 'PalFX'), ('trigger1', 'Time = 0'), ('time', '20'), ('add', '32,16,0'), ('sinadd', '64,32,5,3')]),
                    Section('State 1020 trail', [('type', 'AfterImageTime'), ('trigger1', 'AnimElemTime(8) < 0'), ('time', '2')]),
                    Section('State 1020 sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 2'), ('value', '0,3')]),
                    Section('State 1020 step 2', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 2'), ('x', '20')]),
                    Section('State 1020 step 3', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 3'), ('trigger2', 'AnimElem = 12'), ('x', '10')]),
                    Section('State 1020 step 4', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 4'), ('x', '5')]),
                    Section('State 1020 velocity', [('type', 'VelSet'), ('trigger1', 'AnimElem = 4'), ('x', '13')]),
                    Section('State 1020 hit', [('type', 'HitDef'), ('trigger1', 'AnimElem = 4')] + hit_fields),
                    Section('State 1020 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]),
                ]
                results[number] = (State(number, sd, sections), [])
            elif number == 800:
                hit_body = observed.split('hitdef{', 1)[1].split('}', 1)[0]
                hit_fields = [tuple(part.split(':', 1)) for part in hit_body.split(';') if part]
                sections = [
                    Section('State 800 throw', [('type', 'HitDef'), ('trigger1', 'Time = 0')] + hit_fields),
                    Section('State 800 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]),
                ]
                results[number] = (State(number, sd, sections), [])
            elif number in (1300, 1310, 1320, 1330, 1340, 1350, 1351):
                sections = {
                    1300: [
                        Section('State 1300 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(3) < 0'), ('value', '15,0')]),
                        Section('State 1300 sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '0,1')]),
                        Section('State 1300 reversal', [('type', 'ReversalDef'), ('trigger1', 'Time = 0'), ('reversal.attr', 'SA, AA'), ('pausetime', '0,0'), ('sparkno', '40'), ('sparkxy', '40,0'), ('hitsound', '6,0'), ('p1stateno', '1310'), ('p1sprpriority', '2'), ('p2sprpriority', '1')]),
                        Section('State 1300 hitovr', [('type', 'HitOverride'), ('trigger1', 'Time = 0'), ('attr', 'SA, AP'), ('stateno', '1310'), ('time', '8')]),
                        Section('State 1300 stop rev', [('type', 'ReversalDef'), ('trigger1', 'Time = 4'), ('trigger1', 'command = "holdfwd"'), ('trigger2', 'Time = 8'), ('reversal.attr', '')]),
                        Section('State 1300 stop ovr', [('type', 'HitOverride'), ('trigger1', 'Time = 4'), ('trigger1', 'command = "holdfwd"'), ('trigger2', 'Time = 8'), ('attr', ''), ('time', '0')]),
                        Section('State 1300 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]),
                    ],
                    1310: [
                        Section('State 1310 pause', [('type', 'Pause'), ('trigger1', 'Time = 0'), ('time', '20'), ('endcmdbuftime', '20'), ('pausebg', '0')]),
                        Section('State 1310 invuln', [('type', 'NotHitBy'), ('trigger1', 'Time = 0'), ('value', 'SCA'), ('time', '1')]),
                        Section('State 1310 guard', [('type', 'ChangeState'), ('trigger1', 'Time = 1'), ('trigger1', 'command = "holdback"'), ('value', '130'), ('ctrl', '1')]),
                        Section('State 1310 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]),
                    ],
                    1320: [
                        Section('State 1320 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(3) < 0'), ('value', '10,0')]),
                        Section('State 1320 sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '0,1')]),
                        Section('State 1320 reversal', [('type', 'ReversalDef'), ('trigger1', 'Time = 0'), ('reversal.attr', 'C, AA'), ('pausetime', '0,0'), ('sparkno', '40'), ('sparkxy', '40,0'), ('hitsound', '6,0'), ('p1stateno', '1330'), ('p1sprpriority', '2'), ('p2sprpriority', '1')]),
                        Section('State 1320 stop rev', [('type', 'ReversalDef'), ('trigger1', 'Time = 5'), ('reversal.attr', '')]),
                        Section('State 1320 hitovr', [('type', 'HitOverride'), ('trigger1', 'Time < 5'), ('attr', 'C, AP'), ('stateno', '1330')]),
                        Section('State 1320 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '11'), ('ctrl', '1')]),
                    ],
                    1330: [
                        Section('State 1330 pause', [('type', 'Pause'), ('trigger1', 'Time = 0'), ('time', '20'), ('endcmdbuftime', '20'), ('pausebg', '0')]),
                        Section('State 1330 invuln', [('type', 'NotHitBy'), ('trigger1', 'Time = 0'), ('value', 'SCA'), ('time', '1')]),
                        Section('State 1330 guard', [('type', 'ChangeState'), ('trigger1', 'Time = 1'), ('trigger1', 'command = "holdback"'), ('value', '131'), ('ctrl', '1')]),
                        Section('State 1330 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '11'), ('ctrl', '1')]),
                    ],
                    1340: [
                        Section('State 1340 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(3) < 0'), ('value', '10,0')]),
                        Section('State 1340 sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '0,1')]),
                        Section('State 1340 reversal', [('type', 'ReversalDef'), ('trigger1', 'Time = 0'), ('reversal.attr', 'A, AA'), ('pausetime', '0,0'), ('sparkno', '40'), ('sparkxy', '40,0'), ('hitsound', '6,0'), ('p1stateno', '1350'), ('p1sprpriority', '2'), ('p2sprpriority', '1')]),
                        Section('State 1340 stop rev', [('type', 'ReversalDef'), ('trigger1', 'Time = 5'), ('reversal.attr', '')]),
                        Section('State 1340 hitovr', [('type', 'HitOverride'), ('trigger1', 'Time < 5'), ('attr', 'SA, AP'), ('stateno', '1350')]),
                        Section('State 1340 ctrl', [('type', 'CtrlSet'), ('trigger1', 'AnimElem = 4'), ('value', '1')]),
                        Section('State 1340 gravity', [('type', 'VelAdd'), ('trigger1', '1'), ('y', 'Const(movement.yaccel)')]),
                        Section('State 1340 land', [('type', 'ChangeState'), ('trigger1', '(Pos Y >= 0) && (Vel Y > 0)'), ('value', '1351')]),
                    ],
                    1350: [
                        Section('State 1350 pause', [('type', 'Pause'), ('trigger1', 'Time = 0'), ('time', '20'), ('endcmdbuftime', '20'), ('pausebg', '0')]),
                        Section('State 1350 invuln', [('type', 'NotHitBy'), ('trigger1', 'Time = 0'), ('value', 'SCA'), ('time', '1')]),
                        Section('State 1350 guard', [('type', 'ChangeState'), ('trigger1', 'Time = 1'), ('trigger1', 'command = "holdback"'), ('value', '132'), ('ctrl', '1')]),
                        Section('State 1350 freeze', [('type', 'PosFreeze'), ('trigger1', 'AnimElemTime(3) < 0')]),
                        Section('State 1350 ctrl', [('type', 'CtrlSet'), ('trigger1', 'AnimElem = 3'), ('value', '1')]),
                        Section('State 1350 gravity', [('type', 'VelAdd'), ('trigger1', 'AnimElemTime(3) > 0'), ('y', 'Const(movement.yaccel)')]),
                        Section('State 1350 land', [('type', 'ChangeState'), ('trigger1', '(Pos Y >= 0) && (Vel Y > 0)'), ('value', '1351')]),
                    ],
                    1351: [
                        Section('State 1351 vel', [('type', 'VelSet'), ('trigger1', 'Time = 0'), ('y', '0')]),
                        Section('State 1351 pos', [('type', 'PosSet'), ('trigger1', 'Time = 0'), ('y', '0')]),
                        Section('State 1351 ctrl', [('type', 'CtrlSet'), ('trigger1', 'Time = 3'), ('value', '1')]),
                        Section('State 1351 high', [('type', 'ChangeState'), ('trigger1', 'command = "blocking"'), ('trigger1', 'command != "holddown"'), ('value', '1300')]),
                        Section('State 1351 low', [('type', 'ChangeState'), ('trigger1', 'command = "blocking"'), ('trigger1', 'command = "holddown"'), ('value', '1320')]),
                        Section('State 1351 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]),
                    ],
                }[number]
                results[number] = (State(number, sd, sections), [])
            elif number == 191:
                wood = [('postype', 'p1'), ('accel', '0,.32')]
                sections = [
                    Section('State 191 hold', [('type', 'ChangeAnim'), ('trigger1', 'RoundState = 0'), ('value', '190')]),
                    Section('State 191 intro', [('type', 'AssertSpecial'), ('trigger1', '1'), ('flag', 'Intro')]),
                    Section('State 191 wood 1', [('type', 'Explod'), ('trigger1', 'RoundState != 0'), ('persistent', '0'), ('anim', '191'), ('postype', 'p1'), ('pos', '260,-90'), ('velocity', '-4.2,-7'), ('accel', '0,.32'), ('removetime', '48')]),
                    Section('State 191 wood 2', [('type', 'Explod'), ('trigger1', 'AnimElemTime(7) = 1'), ('anim', '192'), ('postype', 'p1'), ('pos', '60,-70'), ('velocity', '2,-4'), ('accel', '0,.32'), ('removetime', '35')]),
                    Section('State 191 snd 1', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 7'), ('value', 'F5,2'), ('channel', '1')]),
                    Section('State 191 snd 2', [('type', 'PlaySnd'), ('trigger1', 'AnimElemTime(7) = 3'), ('value', 'F5,3'), ('channel', '2')]),
                    Section('State 191 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0')]),
                ]
                results[number] = (State(number, sd, sections), [])
            elif number in (3000, 3050, 3051):
                hits = re.findall(r'hitdef\{([^}]*)\}', observed)
                hit_fields = [[tuple(part.split(':', 1)) for part in hit.split(';') if part] for hit in hits]
                end = Section(f'State {number} end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')])
                if number == 3000:
                    sections = [
                        Section('State 3000 width', [('type', 'Width'), ('trigger1', 'AnimElem = 2, >= 0'), ('value', '15,0')]),
                        Section('State 3000 super', [('type', 'SuperPause'), ('trigger1', 'AnimElem = 2, 1'), ('pos', '25,-57'), ('anim', '100'), ('sound', '20,0'), ('poweradd', '-1000')]),
                        Section('State 3000 afterimage', [('type', 'AfterImage'), ('trigger1', 'AnimElem = 2, 1'), ('time', '2')]),
                        Section('State 3000 trail', [('type', 'AfterImageTime'), ('trigger1', 'AnimElemTime(2) >= 1 && AnimElemTime(25) < 4'), ('time', '2')]),
                        Section('State 3000 immune', [('type', 'NotHitBy'), ('trigger1', 'AnimElem = 2'), ('value', ', NA, SA, AT'), ('time', '11')]),
                        Section('State 3000 step 2', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 2'), ('x', '20')]),
                        Section('State 3000 immune 2', [('type', 'NotHitBy'), ('trigger1', 'AnimElemTime(2) >= 0 && AnimElemTime(14) < 0'), ('value', 'C, NA'), ('time', '1')]),
                        Section('State 3000 sound', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 4'), ('trigger2', 'AnimElem = 12'), ('trigger3', 'AnimElem = 20'), ('value', '0,3')]),
                        Section('State 3000 steps', [('type', 'PosAdd')] + [(f'trigger{i+1}', f'AnimElem = {e}') for i, e in enumerate((3, 11, 13, 19, 21, 31))] + [('x', '10')]),
                        Section('State 3000 velocity', [('type', 'VelSet'), ('trigger1', 'AnimElem = 5'), ('trigger2', 'AnimElem = 13'), ('trigger3', 'AnimElem = 21'), ('x', '6')]),
                        Section('State 3000 step 5', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 5'), ('x', '5')]),
                        Section('State 3000 hit 0', [('type', 'HitDef'), ('trigger1', 'AnimElem = 5'), ('trigger2', 'AnimElem = 13')] + hit_fields[0]),
                        Section('State 3000 hit 1', [('type', 'HitDef'), ('trigger1', 'AnimElem = 21')] + hit_fields[1]),
                        end,
                    ]
                elif number == 3050:
                    sections = [
                        Section('State 3050 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(4) >= 0 && AnimElemTime(16) < 0'), ('value', '5,0')]),
                        Section('State 3050 super', [('type', 'SuperPause'), ('trigger1', 'AnimElem = 2'), ('pos', '-5,-55'), ('anim', '100'), ('sound', '20,0'), ('poweradd', '-1000')]),
                        Section('State 3050 immune', [('type', 'NotHitBy'), ('trigger1', 'AnimElem = 2'), ('value', ', NA, SA, AT'), ('time', '6')]),
                        Section('State 3050 trail', [('type', 'AfterImageTime'), ('trigger1', 'AnimElemTime(2) >= 0'), ('time', '2')]),
                        Section('State 3050 sound', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 4'), ('value', '0,2')]),
                        Section('State 3050 hit', [('type', 'HitDef'), ('trigger1', 'Time = 0')] + hit_fields[0]),
                        Section('State 3050 follow', [('type', 'ChangeState'), ('trigger1', 'MoveHit'), ('value', '3051')]),
                        end,
                    ]
                else:
                    sections = [
                        Section('State 3051 trail', [('type', 'AfterImageTime'), ('trigger1', 'AnimTime < -2'), ('time', '2')]),
                        end,
                    ]
                if len(hits) != {3000: 2, 3050: 1, 3051: 0}[number]:
                    raise ValueError(f"state {number}: unexpected HitDef count")
                results[number] = (State(number, sd, sections), [])
            elif number == 810:
                sections = [
                    Section('State 810 var', [('type', 'VarSet'), ('trigger1', 'Time = 0'), ('var(2)', 'command = "holdfwd"')]),
                    Section('State 810 grab snd', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 2'), ('value', '1,1')]),
                    Section('State 810 throw snd', [('type', 'PlaySnd'), ('trigger1', 'AnimElem = 7'), ('value', '800,0')]),
                    Section('State 810 bind1', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(2) < 0'), ('pos', '28,0')]),
                    Section('State 810 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(2) >= 0 && AnimElemTime(12) < 0'), ('edge', '60,0')]),
                    Section('State 810 bind2', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(2) >= 0 && AnimElemTime(5) < 0'), ('pos', '58,0')]),
                    Section('State 810 bind5', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(5) >= 0 && AnimElemTime(6) < 0'), ('pos', '47,0')]),
                    Section('State 810 turn6', [('type', 'Turn'), ('trigger1', 'var(2)'), ('trigger1', 'AnimElem = 6')]),
                    Section('State 810 pos6', [('type', 'PosAdd'), ('trigger1', 'var(2)'), ('trigger1', 'AnimElem = 6'), ('x', '-37')]),
                    Section('State 810 face6', [('type', 'TargetFacing'), ('trigger1', 'var(2)'), ('trigger1', 'AnimElem = 6'), ('value', '-1')]),
                    Section('State 810 bind6', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(6) >= 0 && AnimElemTime(7) < 0'), ('pos', '41,-60')]),
                    Section('State 810 bind7', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(7) >= 0 && AnimElemTime(8) < 0'), ('pos', '25,-75')]),
                    Section('State 810 bind8', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(8) >= 0 && AnimElemTime(9) < 0'), ('pos', '15,-90')]),
                    Section('State 810 bind9', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(9) >= 0 && AnimElemTime(10) < 0'), ('pos', '-5,-96')]),
                    Section('State 810 bind10', [('type', 'TargetBind'), ('trigger1', 'AnimElemTime(10) >= 0 && AnimElemTime(11) < 0'), ('pos', '-14,-90')]),
                    Section('State 810 bind11', [('type', 'TargetBind'), ('trigger1', 'AnimElem = 11'), ('pos', '-50,-50')]),
                    Section('State 810 hurt11', [('type', 'TargetLifeAdd'), ('trigger1', 'AnimElem = 11'), ('value', '-78')]),
                    Section('State 810 throw11', [('type', 'TargetState'), ('trigger1', 'AnimElem = 11'), ('value', '821')]),
                    Section('State 810 turn12', [('type', 'Turn'), ('trigger1', 'AnimElem = 12')]),
                    Section('State 810 pos15', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 15'), ('x', '-10')]),
                    Section('State 810 end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '0'), ('ctrl', '1')]),
                ]
                results[number] = (State(number, sd, sections), [])
            elif number in (1000, 1010, 1050, 1060):
                hits = re.findall(r'hitdef\{([^}]*)\}', observed)
                if len(hits) != (2 if number in (1000, 1010) else 1):
                    raise ValueError(f"state {number}: unexpected HitDef count")
                sections = [Section(f'State {number} sound', [('type', 'PlaySnd'),
                    ('trigger1', f'Time = {8 if number == 1000 else 9 if number == 1010 else 1}'),
                    ('value', '0,3' if number in (1000, 1010) else '0,2')])]
                if number in (1000, 1010):
                    sections.extend([
                        Section(f'State {number} step 2', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 2'), ('x', '20')]),
                        Section(f'State {number} step 3', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 3'), ('trigger2', 'AnimElem = 13'), ('x', '10')]),
                        Section(f'State {number} step 5', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 5'), ('x', '5')]),
                    ])
                    if number == 1010:
                        sections.append(Section('State 1010 velocity', [('type', 'VelSet'), ('trigger1', 'AnimElem = 5'), ('x', '4')]))
                else:
                    if number == 1060:
                        sections.append(Section('State 1060 step 2', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 2'), ('x', '6')]))
                    sections.append(Section(f'State {number} step 4', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 4'), ('x', '20' if number == 1050 else '21')]))
                for index, hit in enumerate(hits):
                    fields = [tuple(part.split(':', 1)) for part in hit.split(';') if part]
                    triggers = [('trigger1', f'AnimElem = {5 if number in (1000, 1010) else 4}')]
                    if number in (1000, 1010):
                        triggers.append(('trigger1', 'P2BodyDist X < 40' if index == 0 else 'P2BodyDist X >= 40'))
                    sections.append(Section(f'State {number} hit {index}', [('type', 'HitDef')] + triggers + fields))
                if number == 1000:
                    sections.append(Section('State 1000 retreat', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 9'), ('x', '-5')]))
                ending = [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'),
                          ('value', '0' if number in (1000, 1010) else '1051' if number == 1050 else '1061')]
                if number in (1000, 1010): ending.append(('ctrl', '1'))
                sections.append(Section(f'State {number} end', ending))
                results[number] = (State(number, sd, sections), [])
            elif number in (210, 240, 410):
                hits = re.findall(r'hitdef\{([^}]*)\}', observed)
                if len(hits) != (2 if number == 410 else 1):
                    raise ValueError(f"state {number}: unexpected HitDef count")
                sections = []
                if number == 210:
                    sections.append(Section('State 210 width', [('type', 'Width'), ('trigger1', 'AnimElemTime(2) >= 0 && AnimElemTime(7) < 0'), ('value', '15,0')]))
                sections.append(Section(f'State {number} sound', [('type', 'PlaySnd'), ('trigger1', 'Time = 1' if number == 410 else 'Time = 2'), ('value', '0,4' if number == 210 else '0,1')]))
                for index, hit in enumerate(hits):
                    fields = [tuple(part.split(':', 1)) for part in hit.split(';') if part]
                    sections.append(Section(f'State {number} hit {index}', [('type', 'HitDef'), ('trigger1', f'AnimElem = {3 + index}')] + fields))
                if number == 210:
                    sections.extend([
                        Section('State 210 contact', [('type', 'ChangeAnim'), ('trigger1', 'AnimElemTime(5) > 0 && AnimElemTime(6) <= 0'), ('trigger1', 'MoveContact'), ('ignorehitpause', '1'), ('persistent', '0'), ('value', '210'), ('elem', '6')]),
                        Section('State 210 priority', [('type', 'SprPriority'), ('trigger1', 'AnimElem = 5'), ('value', '2')]),
                    ])
                elif number == 240:
                    sections.append(Section('State 240 offset', [('type', 'PosAdd'), ('trigger1', 'AnimElem = 7'), ('x', '12')]))
                sections.append(Section(f'State {number} end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '11' if number == 410 else '0'), ('ctrl', '1')]))
                results[number] = (State(number, sd, sections), [])
            elif number in (600, 610, 630, 640):
                hit_body = observed.split('hitdef{', 1)[1].split('}', 1)[0]
                hit_fields = [tuple(part.split(':', 1)) for part in hit_body.split(';') if part]
                sections = [
                    Section(f'State {number} hit', [('type', 'HitDef'), ('trigger1', f'AnimElem = {3 if number == 610 else 2}')] + hit_fields),
                    Section(f'State {number} sound', [('type', 'PlaySnd'), ('trigger1', f'Time = {2 if number in (610, 640) else 1}'), ('value', '0,1' if number in (610, 640) else '0,0')]),
                ]
                if number == 600:
                    sections.append(Section('State 600 early ctrl', [('type', 'CtrlSet'), ('trigger1', 'AnimElemTime(3) = 2'), ('value', '1')]))
                results[number] = (State(number, sd, sections), [])
            elif number in (200, 230, 400, 430, 440):
                hit_body = observed.split('hitdef{', 1)[1].split('}', 1)[0]
                hit_fields = [tuple(part.split(':', 1)) for part in hit_body.split(';') if part]
                sections = [
                    Section(f'State {number} hit', [('type', 'HitDef'), ('trigger1', f'AnimElem = {2 if number == 400 else 4 if number == 440 else 3}')] + hit_fields),
                    Section(f'State {number} sound', [('type', 'PlaySnd'), ('trigger1', f'Time = {2 if number == 230 else 1}'), ('value', '0,2' if number == 440 else '0,0')]),
                ]
                if number == 400:
                    sections.append(Section('State 400 early ctrl', [('type', 'CtrlSet'), ('trigger1', 'AnimElemTime(3) = 2'), ('value', '1')]))
                sections.append(Section(f'State {number} end', [('type', 'ChangeState'), ('trigger1', 'AnimTime = 0'), ('value', '11' if number in (400, 430, 440) else '0'), ('ctrl', '1')]))
                results[number] = (State(number, sd, sections), [])
            elif number == 1055:
                # Feed the verified ZSS HitDef through the normal CNS compiler
                # so its complete payload and the AnimElem trigger are retained.
                hit_body = observed.split('hitdef{', 1)[1].split('}', 1)[0]
                hit_fields = [tuple(part.split(':', 1)) for part in hit_body.split(';') if part]
                sections = [
                    Section('State 1055 voice', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '100,0')]),
                    Section('State 1055 swing', [('type', 'PlaySnd'), ('trigger1', 'Time = 0'), ('value', '0,1')]),
                    Section('State 1055 offset', [('type', 'PosAdd'), ('trigger1', 'Time = 0'), ('x', '10'), ('y', '-10')]),
                    Section('State 1055 gravity', [('type', 'VelAdd'), ('trigger1', '1'), ('y', '.45')]),
                    Section('State 1055 hit', [('type', 'HitDef'), ('trigger1', 'AnimElem = 5')] + hit_fields),
                    Section('State 1055 landing', [('type', 'ChangeState'), ('trigger1', 'Vel Y > 0 && Pos Y >= -5'), ('value', '1056')]),
                ]
                results[number] = (State(number, sd, sections), [])
            else:
                results[number] = (State(number, sd, []),
                                   _controllers(number, const))
    return results
