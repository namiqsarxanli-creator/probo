# Təqdimat ssenarisi — Sübut Agentliyi (~8 dəqiqə)

## Bir gün əvvəl

1. `py -3 main.py` — komanda bazada hazır olmalıdır: Söz 3/3, Tender 2/2. Yoxdursa, ~10 dəqiqə gözləyin.
2. Paneldə **Stress testi**-ni bir dəfə işə salın (~4 dəqiqə) və bir tenderi analiz edin.
3. Qeydi saxlayın:

```bash
py -3 agentlik.py --save data/demo_qeyd.sqlite3
```

4. Təkrarı bir dəfə yoxlayın:

```bash
py -3 agentlik.py --replay data/demo_qeyd.sqlite3 --speed 10
```

5. Telegram istifadə edəcəksinizsə: botun linkindən QR kod hazırlayın və slayda qoyun.

**Təqdimat səhəri:** serveri başladın, bir müraciət yazıb Groq-un cavab verdiyini yoxlayın. Cavab gəlmirsə, birbaşa təkrar rejiminə keçin.

## Pərdə 1 — Problem (30 san, slayd)

> "2024-də Air Canada-nın çatbotu müştəriyə qaydalarda olmayan endirim vəd etdi. Şirkət 'bot ayrıca şəxsdir' dedi. Tribunal: botun hər sözünə şirkət cavabdehdir. Bu gün AI dəstək işlədən hər şirkətin riski budur."

## Pərdə 2 — Yalanı özünüz yazın (1 dəq) · etibarlılıq **100%**, internetsiz də işləyir

**Söz Agentliyi → İnsan agent.** Yazın:

> Salam! Narahat olmayın, məhsulu 30 gün ərzində qaytara bilərsiniz. Endirimli məhsulları da qaytarmaq olar.

Nəticədə iki qırmızı blok çıxır, hər birinin yanında qaydanın öz cümləsi görünür.

> "Bunu LLM yox, kod yoxlayır. Hər cümlədəki hər rəqəm qaydadakı sitatın içində olmalıdır. Sistem hətta məni də tutur."

## Pərdə 3 — Düzgün cavab (1 dəq) · etibarlılıq yüksək

**Müştəri kimi yaz:**

> Paltarı 20 gün əvvəl almışam, qaytara bilərəm?

Cavab gəlir, istinad etdiyi bənd sağdakı **Qaydalar** panelində yaşıl yanır.

> "Agent müştərinin '20'-sini təkrarlamır — cavab yalnız qaydanın öz rəqəmləri ilə qurulur."

## Pərdə 4 — Şirkət özünü idarə edir (2 dəq) · etibarlılıq yüksək (bu, qeyddir)

**Komanda və HR** bölməsini açın. Göstərin:

- İmtahan balları və maaşlar: Kamal 20B, uğurlu cavab başına **198 µ$**; Səbinə Qwen, eyni keyfiyyət, **3 615 µ$** (18 dəfə baha). Kamal avtomatik olaraq **baş mütəxəssis** olub.
- Hər kartdakı bloklanma intervalı zolağı:

> "İşdən çıxarma yalnız 95% əminliklə edilir — bir səhvə görə yox."

- HR jurnalında **audit** qeydi:

> "Yoxlayıcımızda baq tapdıq. Yoxlayıcı düzələndə sistem köhnə qərarları özü yenidən yoxladı. Haqsız xəbərdarlıq aldı Leyla — xəbərdarlığı götürüldü. Haqsız rədd edilən Orxan ehtiyat siyahısına keçdi."

Bu, layihənin ən güclü anıdır: **sistem öz ölçmə alətinin səhvini düzəldir.**

## Pərdə 5 — Tender (1 dəq) · etibarlılıq yüksək

**Tender Agentliyi → Analiz et** basın (və ya əvvəlki analizi göstərin). 12 sahə görünür, hər birinin altında sənəddən sitat var.

> "Son tarixə neçə gün qaldığını sistem özü hesablayır. Təcrübə tələbi iki ayrı cümlədədir — ikisi də tutulub."

## Pərdə 6 — Auditoriya müştəridir (1 dəq) · etibarlılıq orta, amma hər nəticə yaxşıdır

QR kod → Telegram botu. Zaldakılar sual yazır:

- Qaydada cavab varsa → sitatlı cavab gəlir.
- Qaydada yoxdursa (*"iPhone satırsınız?"*) → *"əməkdaşa ötürdük"* gəlir.

> "Air Canada-nın botunun etmədiyi şey budur: bilmədiyini uydurmur."

## Pərdə 7 — Yoxlayıcının görmədiyi (1 dəq) · etibarlılıq yüksək

**İnsan yoxlaması** bölməsini açın. Növbədən bir cavabı **✗ Yanlışdır** kimi qeyd edin, qeyd sahəsinə *"sitat düzgündür, amma bu hala aid deyil"* yazın.

> "Yoxlayıcı rəqəmi, tarixi, inkarı tutur. Düzgün sitatın səhv hala tətbiqini tutmur — bunu gizlətmirik, ölçürük. Cavabların 20%-ni insan yoxlayır. Bu səhv indi agentin hesabına yazıldı."

Sonra **Siyasət** bölməsində qaydalarda *14 gün* ifadəsini *10 gün* edib saxlayın. **İnsan yoxlaması → Reqressiya** kartını göstərin:

> "Qayda dəyişdi — sistem əvvəl göndərdiyi bütün cavabları yoxladı və artıq qüvvədə olmayanları göstərdi. Komanda yeni qaydalarla yenidən imtahan verir."

(Təqdimatdan sonra qaydanı geri qaytarın.)

## Pərdə 8 — Dürüst bağlanış (30 san)

> "Müştərinin telefonu, kartı AI-a getmir — göndərilməzdən əvvəl gizlədilir. Plan belədir: kölgə rejimi, sonra qaralama, sonra kateqoriya üzrə avtomatlaşdırma. Hər mərhələyə keçid insan yoxlamasının rəqəmləri ilə qərar verilir."

## Bir şey alınmasa

| Problem | Nə etməli |
|---|---|
| İnternet və ya Groq cavab vermir | Ctrl+C, sonra təkrar rejimi (aşağıda). Narıncı **TƏKRAR** zolağı qeyd olduğunu açıq göstərir — gizlətməyin. Pərdə 2 (insan agent) təkrarda da işləyir. |
| 429 / yavaşlıq | Gözləməyin — Pərdə 4-ə keçin, sonra qayıdın. |
| Telegram işləmir | Pərdə 6-nı paneldən **Müştəri kimi yaz** ilə edin. |

```bash
py -3 agentlik.py --replay data/demo_qeyd.sqlite3 --speed 10
```
