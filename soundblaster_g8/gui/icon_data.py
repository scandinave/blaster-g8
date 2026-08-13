"""Alpha masks for the bundled Bootstrap Icons - GENERATED FILE, DO NOT EDIT.

Regenerate with ``python tools/build_icons.py`` after changing anything under
``assets/bootstrap-icons/``.

Source: Bootstrap Icons v1.13.1 (MIT), vendored under
``assets/bootstrap-icons/``. Each entry is one 8-bit alpha mask per size,
zlib-compressed then base85-encoded: ``MASKS[icon][size]`` holds ``size *
size`` bytes of coverage, row by row, which :mod:`soundblaster_g8.gui.icons`
tints at runtime.
"""

import base64
import zlib

BOOTSTRAP_ICONS_VERSION = "1.13.1"

#: Pixel sizes available for every icon.
SIZES = (14, 15, 16, 18, 22)

_PACKED: dict[str, dict[int, str]] = {
    "activity": {
        14: "c-muNKnE;J$h?rt$h-|t4G|onn@PP0UUn1DT^0y4tGxWG8pBc#28QJF@~q7A@<av(kEIN1SIf&YAS#&e@HS^5^!6p(5JB(^pKd_5^Ku9>Pk|Z3!3+QkKo@)",
        15: "c-muNzy$m#JeC)F$XxFq-N@V(1&^2!JiZs4yIc|6<T(tni=gcL|NsBCX5fCo&0zEA|NpyC(Zw+gbCVDn+;(z27eH{C9u_Z0wygVyH!@f6ISYzQ`LOtf0RZk68v_",
        16: "c-muNAObWup>UZVKVm}WJD)x0h|FJ5P&f~X%k@q|>@63RlUrUsdm978wnzpBqw@0doYIbt4nqcpNRZgFj*b$jGR`*=V(+<;44Ge0I3L*#r?cmrP~7zBF^ZcQnwp6583O<;1|B^",
        18: "c-muNAQtrLqX|g=nSmx!_T(Kqs>r4IyFn-dhF^J`)}xxcghAz}2#i<V(b4hBoq^$a76Suw1CUcy1tjX385pvTGcb6(0&*&0YK4BNGc4^zF>FI4_h$nXk>L9YS5e)>{_aT`n!{)Ql|>WL?<P867yt+QCE5",
        22: "c-muNAQ^CKU=wZl%!5Vr*8f;cLF@mIcVUXoxF7#l23?TtO#}Dm5_Hj^|7r|NuAqyqKgPh|{$CFvFl7}G{LExvV1CvE<O(hU@h49Pk&6X@0zJ=|85lBug7}jVy7d3MF)$oohi>}C#SAL{0?|cFzwk7^V@DU2`V)6&I;IbIJ^pWvDH`|x4kM;0&*yq<p{&M1dVDbe0Mh?B$^",
    },
    "arrow-counterclockwise": {
        14: "c-muN00Nc{1_a>S^52RV&a?aUf5q)t0x+)5JqG67^I)zw69WS$kj|S4(sYLjqJa4>4+DeMa+vznX2`rXra+aqnIRmOyIeqWb}ochGz~-woX=wc%H*Hr0}Bewy1Q=O-RXQV{oJO;+zgli00}l5Yy",
        15: "c-muN00EP51|$&jwSx=66L|K2^UM7XaK7}J21eKG`Cv9TBM|E`FbLlO%O5a+s`1zdBzRshLb*(@I2jle&cltkA`R4rB+CKP>jLF^?E#UF*Mz`4k(;()y5PDS69bdyjU1>d`#rBNz20qya3+U52Lm<$0AIo%MF",
        16: "c-muN00EX(24uju<v$94?f?Hj&lYhY%d^?8yDSSAU}*soC6~b}5(8nP>kC2Td21No?lh2K{K*F6bA1K#*<pNc5TD_k4UF$_3PcvKh4DA#fk=)kB@k}qMTkzh%j@kqxg0iLl!2<_C_MH3`^kI`1|k3e#*8D%",
        18: "c-muN00Wjr22>!p`#-9H=*|ECcTRCe5@Brk|37o;>qBx#Vv*k&7<lGBk%t-rBGf^|+=E~Nmz!{vyl)&q)YQoc%`+x~$la+3k*pmUBHKaa<S7V|nG?V!zv6)j@V#{aJMZuum_z69gD~Wu%;5#AnEyx?DkpdF&5Z2qnQsrsB209ew0+w|2L_@6032;CTL",
        22: "c-muNfC83s223Eh`#+|j%C-OhZDi3!Py7dg+htrRqQVFM|5x*#_5H2^iZI(ekhu!SKcEUTgn|gJ6L+A7q;w<6DSj`7Fz!r8)-vZNn3DbPi7e{(UlK&w{#QX3)%b4#5miPO)r5%3pqdcyUjj_uo`Ebn_d0|w|0a(RRQ^!}VQ}3&2KPSCsau>-rs2n93Q#|se6J7JW_b7eY+rQ^zqvo|=p$LdRdNFqk~c~?(Lz|#!d#qz8~^|+@k6x",
    },
    "chat-square-dots": {
        14: "c-qT<d>0NL=RD?QfCH|__Zg7DeRQ7GBuR$kL@)*9x&L=%IDQmNfm8|u^>c!$`}j;bS(TRN1Y$X-rB$C0EA8mmU&_Exwy&e3R174{ebL6^GA~@c_Kh3bNZQTKAT$7bVlP|",
        15: "c-l*R^$r1E#lDhcKme(i?-`K6drYp42m`AdD}#tNn5+DM0Ymct1cpWb6+v9)G7|>z1~CTHQYLJAk+~mOk$7zHC!brjYOyhpX}WmTs`C>W3|(BJ9?3DtJ&JU3F@PvaILUP+0ZG&RTl0}k<Ot$`FaSY&HWm",
        16: "c-jkk{T~Uu3V3b8fCS86{AWM`|B2wAK7qg>{)wXq{GU|wUYa9wEuROx`2YX!CN2gB?k#`+|9{~J5@lVyfPrDbB38IE&I<{NH+hltX}x--jbg42j0*s&{XM7",
        18: "c-phP^&bV?G{04+gaR6_|5so@0gC_8MHH}$@P_j+Fj!hJfEi$szW+T8!oPnBff-;C?<<}RESokkgBc3Mnv5p$-4Ip8=-agWb7s!$Qw4F<`)AIaeSb1jL`z4<(pNGJ3^K2mbab?YGeOiYIL^v)cpkED?yKz`SGZ6N)c*8I3)Kn+c{vyh0KLdgCI",
        22: "c-j+L|LZ>*__bDO!}I(!G*Iwj&Cgs043PKze*&gx!he!Qr9o_7UIr)=B0BT`bOr|Xj~~^bOo-^k|K}MPg8u&xfHEPXrc+HA7+7kmnW0QF+(4x0!=+5<g3QbBMgDnp_wL>6Evz6uTiXpF=k=d(2K|bTj*cncr-MYNf13j2ROrEU#s80BV2Hr5Wd3Ijm5=k$t>C_L{`^&L4CiRQex-%!NCq}G1RDTzB6TM",
    },
    "crosshair": {
        14: "c-muN00O3>LM8?%kedGB(c}BmB*7eun+a^zR%}VP%s?_XH6cp0Z;CT8OizI6NS(sKbf1lZL1x)9X$A(42aIKpZ5bGr|Np;)fx+%+Ny%dy28Lx|p3T!DuuADAi=}`n?=vz?ONN<}F^Pde@|HG)qkB^fNSfVB<*>Hq$hc(!78IZI;K`E*lf+;;7z^?t3;@ZdE;0",
        15: "c-loz%MF4+5PiGLMM_Yy6G+esP(q@{j!ZOmp(O5sBgjG(#)Gi}SQ{Yg@KNXRGH>3z`2cN*hrl;jROm*lkaf&XGMAr)mrJ|Vl6_xhM@blEY%p=P0t%P1+0G&KGl+^4dmB9ktct(P71$bM)_^omQPD<6n`+#tP#(D^8)BHJK$!m~mjSJlho19O++8J=Z(XcK8ISs|<*jb&G{FCh`!L`GcoH=g",
        16: "c-muN0E6Np1_Y4ly7ueW)eb2rH}-Y6L3x>B@2e;X_r4}XT<2jVNbzeem_FTCk_-%8-3WvF+ZY(G82}kUuU`cKDU(YKxxYX*z5f6I1&}KFnN#|!63BS<|NnC!Rr9li;i@5!5%BVbACNM=$iUFii!g6u3j>4HD;*eD|CI!gjC`mI<vt1n(~+<GO{ywQC%y`Us*`NH{PX9f76~LT78ODn07gMPLj",
        18: "c-muNfPnfs24o;nvFqKtU1j1hK4baUo!RTxXYc+}%m@)!aNml7K~;r;!S>-?uu%CuDVS>M2Sp$=zFHv+wEH5)z)-Oh%+}KbQ+rDo7<OfYSd0JvUjU->wlh?}S*^;zp!**Pv>6!G*1WE&db3&uDxw9nan0*WsICS7|IY={`P+e(?*<#GqYb9^7c(%3f3Zc_?)X_0NESboh6%_#$_M*m?n67EEkGL`AJ2k%tmw<$yp0?4_J7W2gsB!Q+41Jh_F_?#AgY6h7yw|}Oeg",
        22: "c-m!=!D_-l5Qg_=k{0_4lAuB9b4Y@|k_m}mi{7f}vDWsi>2nCdQ%hhW5YS6E*+Uy|cDl2v8rwN!|NWNvX2TM4tl5<OEw$^%vENb3?5fWp;XHxN(@yY~ehqZ;ydcJX9<`2;t!pU3c0FWG39sq8dX`ngNJ{#jwek!jcd?NVF0V68g{lj>+;oD#mZ1S+^^*dA0~{<Fw=S8`bdJMcLDUM3PZ=GLY5IsXK)OUa&*%g33WI$RhPI45M+m`?*;*|NXoAoy+1=&MMyw*fUaps6ec!`Hi^9?$-)!Dg8ConvwT8R;=EM9wZ$|mBL0%Tb9PQuDQ=8_du;qLQtf!V|D7F*Fj#c^hbkoT>{{RAcaqR",
    },
    "gear-fill": {
        14: "c-mb~+Yy355K9f-QHJ0sKAPhIu}H<&AYd16%pqUqV<(yHCJPA3<L>dpK0`$YtacIyvys9`%Yn=|!<I7N<g>0jasYfOu>hQ8@HefLG3+SPUNx$y8j*_+Wao6zlZBg7Ud^eWQvMpYW<%tIebzGb6ly7uZsu2$_UtC|1<cfByZ",
        15: "c-mEuO%8%E5QS%1Sn*R2pw&~N=ur%b7f~q}0Rn-#=tAPA<150#Su}6@y_we%`MP{gv{b5SW7$eliSGtiwanaBu8)cKj@NQK;1XiEk2s&`B%D`4qF`<$oh_KabzqonKEd>u6a3Ko2s(NizCg2iwg@P^G1op=!(>XcY(D(wCcV=Qbgf+%0moaCcymfBTECG`*-v}{3K?^X",
        16: "c-mD@K@NgI3>@yFkq3wp_@+wufUIAT5bxq9BtAt6`VH8zMMa%M+i9lL7EmOQHpUxX02tB$Gf(M-w(QBiw5+8ucO2oSA~=6}rSnI!+bqJgBMWif%j{bFsd$*=uDVcpq*c>uT#o!28_{o-XX3MqfKqb0in4z21ML64fIs*6a&PTUg=o7&<?Qg#1jxx8@INmiZf?=5dIAsWgLD",
        18: "c-m!<%?*M;5QV1>2wH=Ro(%CWSP%qlM-ia}1DY5j!5&bt1mJ+{JTznt@3L>dncevzYBhTmI{hgWBIquQn{TZfAsW}(X9h?nBwax~nRp-;Tp7hB&Lzl(%|#(n6E+T)4d0xhAf#3NeK;+Ud;C_7;O|d~#PInf;8sc%U{Ld`!-&Y`K%x;1Q#Lk2E96$EbKO<<<qmhfDH0GP-I@+2wM{RbcMAyQZM4!K`S@o)zc!|H",
        22: "c-n1|OAdlS42GKsvJf}E?x1)Kf?=unU?Ce{(Ibj*1rp*BBnAOJfx}2U#t7O?+i%kTZ3p0O^DLc0)ufE`O!@*nM+4aN!ZrY!(-rW_ndj$7bI)fy>L6Y6irGj9tPI(JTAa%CDAat616`Jl5F?jHI-pR{z*t4hb`sbRD$_;Th>~o2C;yZMRfO^_{YPUfA#Vt3Qj$)fwnep2Mc6!}+M3Sc;d?l$E9UuYUa!0b%?rco#{Iw7Ss?93oVh0|Ab)95i?&tNY>}>t3ohD~A4;X4kDDd&_>;T<-v#){",
    },
    "mic-fill": {
        14: "c-muNU|?Wu{`jGRkpT)~{sTccj5i0wn+@a52l3`(<B7;Yc=943UP3*DS04}Jg?CQ?@p^hgKs?#Yx?leP|Ezsg3aoL`WS!m~?P+}wV^}6!?eD+Z#|*PVdiHE71_UT5fHR}--hK1t?%gOL697(2K)e",
        15: "c-muN00OhK|IU~&zyR;-|NsBL<biQL{)2!Uj2i&v1`xwlS^(uPR0MJL5BPz(z6bR{T#<(ge}KH-a!-W7s&_>c{rUepKV}<5v-+bbd2jichbmB$)pk5S^mv;J+?5PM9|akZ!FvQ#?d`jF|K7cO15ynDqee<v",
        16: "c-muN00NGwpFT}yXMlsL|AAl<g8vD`e~;k*2LodH$uNF0R2IgEs`$?J5o|usR|x;G&twpPLco3qKj@m+qz~^Wh~M;u8rXf^kDDjpW(VB9fP>$^@AqXu0u2oe3^@5uA@)B8u>r{fRGt",
        18: "c-muN00EIDU%o69Vn6_<lmCI>7!yLo;XfGIB1GaLBJl{31c*oiDIzg$FcJ4?h{*f~m`KBXh{%l2V2DUy_cVw|)?vX9Ac1%M$1@-zBA?tm-U9_(JwFOVjZS*!E)W#R@AW<rZhO+FV?DjcKOwn?K{(_5xpZL$6wu#~%wtnhQkpjpNU*^~GX6tBI*11V!7^(%",
        22: "c-muNfB^k%-@k3uV?YIFU;YEZ7h_b>lmEfsD2kvkMDYJVL1a+{sOWzMYKpQWi88XoM9<|SMDx$WMDI5sL>unIL~pf;!9+zmZ@@&iY-P9#5xmH-b0bVN?U#bvZ;;?`XO-W{Fj3C?``KJC164Y+AG*r{cbdi514;~HVhk#WzL+8T!s6cV?cLowe%~=e2{g`>O&>mNOyXcb2kX}}U;!ASlBsEFY3I)aiBt)MXv%*$NCFE00R9f3M*",
    },
    "pci-card-sound": {
        14: "c-oT^Vn6~r_8{{V_M`CbmLovE!hbM$_WytX-~azXydP_Fl>Y7s*$LsDSM62!DnGdy8}H{@pvt{LyC6Iuc=7-L#D75E!|n+a`uZnK=<Vp}s8HA+|NsB``~UyX2iY#WhtI`D*}%m`4(u3SWS0Q|b8}gA",
        15: "c-rIPVn7CGZ=i4m?xS*FxF7*@f&XxD{r~@e5bn>+wg2zS{rvwQ%yr?B>R(#wehA9dc;3)|-X?Vwl<NkRT~h9L7|Q+sGkg92`|`hFTrju+GWmsHSy@>e5C?<py{`k5s0U(ikgIsEFvu&(uqi1iF@aslisEJf83<;(",
        16: "c-muNKm|`fp$Ysa#7BTX|Nno2^1sde|9?q2kOAhO?J#2aKjEy<A1J@UW+B7>#7PQwVSJaR4F3}l{Bz|74FCHP>Vf9X`Tu_r+&n1w{r~?*pnJ;8%WZ(T9Ok}H|Nj?$1WAFxV+Onc0I4-}&H",
        18: "c-muNKnJI9Yodu5zi>cTbRSb>W;qJTWVrty0gi$Qn8+2k_y50(?176khw?GpU)oWU2p2Jk+r@Byo5FGnB$1sA_qQq{iL`)pE$Kwk1vJ_H1B%H|a2R6yvJMnb0QAMwckkY10P(v>n7`6?@7`s(b@%SwW)P9}8VrO00InO91O",
        22: "c-muNzy?}o#$XX$@@zjg#q&uKy<3g}k{IUyM*(j@#6N`SzvXZL|9>oU9K?o+zIz_bu<-xQp9aB5q6-)p1Q_OjmF(!^`-c$i=U(*?$c(Ys%<vjT^Z}3=ZHpqh5NyI1iLOq5BoqF>2itb*r+x^s8-Olb1$Nm9R8dr4JnX;#X`s;AeCEuV{k~^FKnf9Nw}6^nMu81L5>;_=anWFP1d=AOko1aXAQk`snr+<_",
    },
    "play-fill": {
        14: "c-muNAOXZ(^+Vz{{QtjK7n%3}_e>Ea-v9rv>><2*Fz>Y;4wXozL|^e^AQ=Dv_-i3x",
        15: "c-muNAPtDGc0uMk{Qti}8HM}**F-*K?*IQ!<50N&|Ldd3#^ThAY_iyL7Y4Eb00;6WIR",
        16: "c-muNARWY8qw@d#TP};t|NsC0*A5;O{{R1v;}}u+|Nn2p%STm@VjjAEk=6`k0{{>VE0X",
        18: "c-muNARBO^3&j7PEQBi3@c;k2d=@m3|NpOhpo{$fzgY=g<o|b13=t0kx~_ZTwLR|l6k#++volZ(06R@L6a",
        22: "c-muNpe0ae#UdF0|C&3dXv6>i|95L)6aD{dA|Dpf|Nmd-Gh-3`|No3NHqrn8g0PAP5^2J-G$!I)hUtq~tUhK?VPT*P0050nQeg",
    },
    "record-circle": {
        14: "c-lRUK?;Ik6olsr(w~TWfJE;jD76;RV<;$EohodX>B@iccZY2KH;Ofj_vRbs@c_8>sMJt7Sah5c129q<6Hd3?8bWjt+-U<~FYP+v4lZY(D=SCd1Rt$ukKJA|yK1VXdHtzbXkgQywSFJid{ikjuWbm(3rC9I2UA*zyA92I$Qj9uEOHsHp<O<e>I;kZ3nGL$a{",
        15: "c-muNU|>zy{rcVOUGc08AfS19l>-|Co5Sjh>Oh{>BVPsx@PDYzz<Sw_0R{rjvm~qnF%<mdLDZVq-S$AL<nRAKML^nV`)hWf+@Jsd|NoI=VBmQ99w_MZ9|XLCtoN^gvhpC=-?9u0oG*7d00oQw{QsQ~q@B0LuLc<@=Pd`K)<&~j^oQFUbdH%p{b2x%_dpd$s$W>+#KFMfyzZPTSd=AZ`>S`awnZ}o*#InCLHY",
        16: "c-lpd%?g4*6h^NLb4-1Zq(t=D6zVC&pTP`@Lcym9gx(>^R+VeZmFA-El;yYi&Y63e82|t?I(J<W8t}<@bFn5ouiDp@$n>z2z5_YV@L;{=pbwWU!MsTDk9^Z33!4OW?Fk5TT1>El7sf@H<=qIYW?mr(&6D}#=cGBQSRQi+K|6*vTXXM~!|q%7##J8PQ%Vh@c=%6B0mLlnH<WZwu*B##p9;ckQBv|9=rnKJ+}9Yt0k*nJ2L",
        18: "c-muNU|?YKUUvV_@B2%=7#Scy=k&8S7gbf)_U9+Hzyi*n+BqRoT-_fXK`K7QGr&R8M@<H%)9nmMpyxQF&oi(Vq0kUP5Y7F<V_6%B;r;Rd{|_D@R`<gDE+7>^f&c&C3jmq!cYdn^sgVC*5C~+d{RE2yBSh4H-ggC3f*(Kv@A!dCk2_1jmV3Mh3b=x;U*Pqe3&aoz3IwTO;CbcFc(NPWh5bhv8MHnoAp}xCY5+;ck3HNFKF@@Y4q%4n@t581YHA)mua0U!)iQc4y!-3dodxdT5CZ^N;$Hy",
        22: "c-mEv&2EA~6oqFgZd&=POC!PbJsM5lqYW`GjC+FtU6}Ydg+L#}W*pf|unzzZMu?QTGgUmB`<*j$@BARdq|L(P^_m1z72VX{<kYh*YvJc~Es4;K()km|j-Blc9{ytE-e;1e&)Op_qlQ$1>mi%eKo1(6R!Ga|!gad>oJ^U~XTbM;Rgn>(oKL<z9+p+DVhASijyAx)0%1NPE<ad(sf0A<tV{XHs{Ws<JWUqRM0ofE#ytc+z^H)J-oS)kQ`!L<;(8|!mGfAowz#~m3s|NyT4(0ti(jdOkhCLeGt{DOt1d=D292Fj+ym(2lOsM;S<-D!tV^pb4_wP~!*lAi?tSvakBj2qjrldvAG~ai1^",
    },
    "sliders": {
        14: "c-muNfC2##1_UU$eXWauAq@gDZ*wxAEKBQvfbQ$e4Ev{bz*Kgf+P@4$TWwgO0i-kxKpdglHs05mp(^e^S<b+4^8Q^2VBonKmv@>GZj*9vn-~KFlXoyX!uA!b=N)8Xm<a)MFEB7{UOCeR0^IM4^IQpbfvF6+_b`)z0RXy;HhT",
        15: "c-muNfB|l11_WSV`SO`R1A{RXG%jOOeP(978w&2^FfiQPw;QI|>|WBOePEVDlpv6_no`3D;!Qa|@4hrlQF-+fHir5w<uFk7jEkXt1B}PO(0pyv4N)W)=z4GhNv~!7NP_k^1L{vPFr0ycr<n{4x6hwZf`Xz=941dxm0*gQr@g=9$iM&qk{&(#",
        16: "c-muNzyVZ`|2?LR#6ModR&s=a;XfR(F>nG&xct#l_VPnW>XncDIjn@oASi$v1O<2uqKW$eEj&i3",
        18: "c-muNzzvwnubfLn5vjNzn(!`!fng>byae*fZ_k|B0S6D`85o)_c61<gCBCg_{^9^;G8&pQgXqvrYaGD>e1|^0yCj8dN5?^K)>TUo{Qv*|r!g>i{6_#KrMVlK8K!Slf&&Hyi5qvXJyl0>EW2L_FNn69)T@Oe;rC_Q!p}ww3~6w1Er)@j|6p3$ZaDbp%fOKTV)t$&cU>@ddYpn{!IaN$Y8e?A06))Jw*",
        22: "c-muNAPAUar}r3O2yXd%{QmE7G|}k4E)2|z-f=Q8+(iQKPXeWM{y)BZw*v_ry3fqO;P!t?M+dSA`o9<HxZOR5Ze7H?|NoCmLpgqHchqo$SzK0HFcl^L53Tref*n<x!1s0r27_Oz$YTG2Kn+Nr_>T<I(n|gZFfeewT$6?bfXcSNO7-3MSpm&G0;~S~zixvWR=iRWT5|5qvpI}tlKl6c^ez6=1!O59fyOVgK-d2^P*Os1&=H_AH4wuE3CwsW$iR^NH_*ie*<A5gm-E`b%|myK=8m5)JJ^5>0Q>odmH",
    },
    "soundwave": {
        14: "c-muNzyefJc=wRlfgJb6ouF(1&ixAa9p(#g0@>Ueb#Y)`U7P_kgTwrW1TYUoq4BuX;VSi*fjapirtot@O%33<FXn{9b_NC&Y|aG$Y^)$^",
        15: "c-muNzy>(kP`EYONE}|Nh5|WGI5)npp<up0l%w5|&=2GWOqBz2MAtg3hj8~B?BrxnIFI1o7hn)wiQsMp8K>O_;ZBxAGI^dK+#(*yh5}hmB!^UIqd1a-4XalGV+JKY",
        16: "c-muNAPzi5<NrsK{g0#~8OQ^{WE37u<Ub0;<R>EW62T@UqVPcAF_8Bdk9!!<WN`xkC(9~F",
        18: "c-muNAOS4rMHl(6fWj4w0*d&^BZ)ZN2a4=Zfb+u(pd#S~V1A)t!+fYn!+hCRpa_To7XdP`i4+<j>uLd;6qXMa3CqW6JJ5xZAQ#Hv^#u?t<0T<j0N~g)hy",
        22: "c-muNAPZ=-ViWxpg-!H-0)~*ADNvL*hZ$9L|9qgR{eO8RAq5YJsKb8+AQJ-E8S3xBMS)CKCZM3fcaetsa8V$0eJ@ZH!bB1UGI5C-d_yx~Z4bycHZ<E<m>{l@cY})pnfQGH1g;<-^JFs<6FQ)fjKn6Y$x2pa0RW(!Pz3",
    },
    "volume-up-fill": {
        14: "c-muNzzUdok$G;rnIH_!bK(q*{tJ?TOnu{+PyZDf)NZL>VqlQ_4+09UCA0lc$}lKEc$zy?Y8TqWcv?GCY8KkTRJIq-@jEFEGo@brrpg7V4QIs|8hsZfBHO-`38%}z003(XGA9",
        15: "c-muNzyVlLxijNotoUdKj&8*#(qInj<p2G=+Dj{{dKefuuikzB|9`*bO}Qu14;UB({)0e2!#3w*y7z?P+`go>&SzBM-0e=sb?*x^a9#%MwYnkqMCLxiWUZxTRozf~<DwWix|E(sA-if;EIv1b0RWYnIiU",
        16: "c-muNAQo`!mx3`l(-;_Jt!j2ax$<ZKGjKRO6Tj*N<m8suy#D{6;h@vBrp(1a{(mrF2t8nQRrw);&-sJ>7wd0kBt9DoKYYLORTYr>(vB{$c@8rgvlk)R=lE3Yh9k^9$w2p5)^A63?><Q)d<6gngF$@",
        18: "c-muNAPx9AAaU41IPHxTjL$OR3Il`A9nlp_p#q}&|KDeD=HED9@uwV+yZFqRSO0+`+h?i#l-N@M6uJK&1nx6v{^UO$Q@0FBgyD(p!iM;R$RbZ|7uKVQX#eCt6Ajh{GkNC>wV&d9^B}g19RS(Rw|TDePg$4?Cte1+@V3b6MF?N8f_#zrS`yu-_QZw>0MbZO)c",
        22: "c-muNAR7oUVG(3L*N4Iv;RO=H?CJmgkp%5uPGewTJid@&!vl7>VBYWl^BF|=!v6cK{Yd}`=#`h3uloNVD7t?g!`AZ*+xCD&=l_R*`3(O5?cDxrXZ+wm5oNeOjs0h;*?&D$(FF$>?l#N*cR>|hh*k8)RImxUD58P?ZQTBAW&8j+SO@O118W$zo@3ay8_gHI;s1Tr{=}jC_{3a>P50Q40z#M@M6hN5_rVsD-9(2vegFXOEqnX",
    },
}

#: ``{icon name: {size: alpha mask}}``, unpacked once at import.
MASKS: dict[str, dict[int, bytes]] = {
    name: {size: zlib.decompress(base64.b85decode(packed)) for size, packed in by_size.items()}
    for name, by_size in _PACKED.items()
}
