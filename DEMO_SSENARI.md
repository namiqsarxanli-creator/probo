# Təqdimat ssenarisi — Sübut Agentliyi (~8 dəqiqə)

## Quruluş: iki tab

| Tab | Nə göstərir | Əmr |
|---|---|---|
| **Canlı** — http://127.0.0.1:8830 | Zalın gözü qarşısında yeni müraciət, insan agent, tender | PyCharm-da `main.py` → Run |
| **Qeyd** — http://127.0.0.1:8831 | 07.10.2026-da canlı Groq ilə qeydə alınmış sessiya: audit, xəbərdarlıq, reqressiya | aşağıdakı əmr |

İkinci terminalda (PowerShell):

```powershell
$env:PORT=8831; py -3 agentlik.py --replay data/demo_qeyd.sqlite3 --speed 10
```

Qeyd ~80 saniyə oynayır. Sonunda dayanır. Yuxarıdakı **Əvvəldən** düyməsi qeydi yenidən başladır.

## Bir gün əvvəl

1. `py -3 main.py`. Komandanın bazada hazır olduğunu yoxlayın: Söz 3/3, Tender 2/2.
2. Qeydi bir dəfə sona qədər izləyin (yuxarıdakı əmr).
3. Telegram istifadə edəcəksinizsə: tokeni `.env`-ə yazın və `main.py`-ı yenidən başladın. QR kod paneldə **Müştəri kimi yaz** kartında avtomatik çıxır. Böyütmək üçün QR-a klikləyin və ya slayda qoymaq üçün http://127.0.0.1:8830/api/telegram/qr.svg ünvanını açın.

**Təqdimat səhəri:** canlı tabda bir müraciət yazın və Groq-un cavab verdiyini yoxlayın. Cavab gəlmirsə, hər şeyi qeyd tabından göstərin.

## Pərdə 1 — Problem (30 san, slayd)

> "2024-də Air Canada-nın çatbotu müştəriyə qaydalarda olmayan endirim vəd etdi. Şirkət 'bot ayrıca şəxsdir' dedi. Tribunal: botun hər sözünə şirkət cavabdehdir."

## Pərdə 2 — Yalanı özünüz yazın (1 dəq) · canlı tab, internetsiz də işləyir

**Söz Agentliyi → İnsan agent.** Yazın:

> Salam! Narahat olmayın, məhsulu 30 gün ərzində qaytara bilərsiniz. Endirimli məhsulları da qaytarmaq olar.

İki qırmızı blok çıxır, hər birinin yanında qaydanın öz cümləsi görünür. Sonra eyni yalanı sözlə yazın: *"otuz gün ərzində"* — o da tutulur.

> "Bunu LLM yox, kod yoxlayır. Sistem hətta məni də tutur."

## Pərdə 3 — Düzgün cavab və gizli məlumat (1 dəq) · canlı tab

**Müştəri kimi yaz:**

> Salam, nömrəm 050 123 45 67. Paltarı 20 gün əvvəl almışam, qaytara bilərəm?

Cavab gəlir. İstinad etdiyi bənd sağdakı **Qaydalar** panelində yaşıl yanır. Kartda **🔒 AI-a gizlədilib: telefon** yazısı görünür.

> "Telefon nömrəsi AI-a getmədi — göndərilməzdən əvvəl gizlədildi. Agent müştərinin '20'-sini də təkrarlamır."

## Pərdə 4 — Şirkət özünü idarə edir (1.5 dəq) · qeyd tabı

**Komanda və HR** bölməsi. Qeyd oynayarkən göstərin:

- Kamal (GPT-OSS 20B) ən ucuz işçidir və baş mütəxəssisdir. Səbinə (Qwen) eyni işi ~18 dəfə baha görür.
- Hər kartdakı bloklanma intervalı zolağı:

> "İşdən çıxarma yalnız 95% əminliklə edilir — bir səhvə görə yox."

- HR jurnalında **audit** qeydləri:

> "Yoxlayıcımızda baq tapdıq. Düzəldəndən sonra sistem köhnə qərarları özü yenidən yoxladı: Leylanın haqsız xəbərdarlığı götürüldü, haqsız rədd edilən Orxan ehtiyata keçdi."

## Pərdə 5 — Yoxlayıcının görmədiyi (1.5 dəq) · qeyd tabı

**İnsan yoxlaması** bölməsi. **Son qərarlar**da:

> Müştəri: *"Gəncəyə göndərirsiniz?"* Kamal: *"Xaricə çatdırılma həyata keçirilmir."*

> "Sitat qaydada hərfən var — yoxlayıcı keçirdi. Amma Gəncə xaricdə deyil. Bunu kod görə bilməz, ona görə cavabların 20%-ni insan yoxlayır. Bu səhv Kamalın hesabına yazıldı — və Kamal xəbərdarlıq aldı, baş mütəxəssislik başqasına keçdi."

**Komanda və HR**-da Kamalın kartını göstərin: bloklanma səbəbləri arasında «insan yoxlamasında yanlış tapıldı».

Sonra **Reqressiya** kartı:

> "Mağaza çatdırılma qiymətini 5-dən 7 manata qaldırdı. Sistem əvvəl göndərdiyi 36 cavabı yenidən yoxladı və birini tapdı: '50 manatdan yuxarı pulsuzdur' — bu söz artıq qüvvədə deyil. Gəncə sualı da yenidən soruşuldu, indi düzgün cavab gəldi."

## Pərdə 6 — Tender (1 dəq) · canlı tab

**Tender Agentliyi** → *Mərkəzi Bank — inkassasiya avtomobilləri (real, 2022)* sənədini seçin. Analiz artıq hazırdır; **Analiz et** ilə yenidən də işlədə bilərsiniz.

> "Bu, Mərkəzi Bankın real elanıdır. Sənəddə olan 8 sahənin hər biri sitatla təsdiqləndi. Cərimə və icra təminatı elanda yoxdur — sistem uydurmadı, 'tapılmadı' dedi. Son tarix keçib — bunu da özü hesabladı."

## Pərdə 7 — Auditoriya müştəridir (1 dəq) · yalnız token varsa

Paneldəki QR → Telegram botu. Zaldakılar sual yazır:

- Qaydada cavab varsa → sitatlı cavab gəlir.
- Qaydada yoxdursa (*"iPhone satırsınız?"*) → *"əməkdaşa ötürdük"* gəlir.

## Pərdə 8 — Dürüst bağlanış (30 san)

> "Yoxlayıcı rəqəmi, tarixi, inkarı tutur. Səhv hala tətbiq olunmuş düzgün sitatı tutmur — onu insan auditi ilə ölçürük və səhv edəni HR cəzalandırır. Real şirkətdə yol belədir: kölgə rejimi, sonra qaralama, sonra avtomatik. Hər addıma keçid insan yoxlamasının rəqəmləri ilə qərar verilir."

## Bir şey alınmasa

| Problem | Nə etməli |
|---|---|
| İnternet və ya Groq cavab vermir | Hər şeyi qeyd tabından göstərin. Narıncı **TƏKRAR** zolağı bunun qeyd olduğunu açıq deyir — gizlətməyin. Pərdə 2 (insan agent) internetsiz də işləyir. |
| 429 / yavaşlıq | Gözləməyin — qeyd tabına keçin, sonra qayıdın. |
| Telegram işləmir | Pərdə 7-ni keçin, **Müştəri kimi yaz** kifayətdir. |

Qeyddə HR jurnalının iki mətni düzəlişdən əvvəlki formadadır: *"Leyla-ə"* və Səbinə üçün *"xərc ən aşağıdır"*. O anda Səbinə bu meyara cavab verən yeganə işçi idi; indiki kod bunu düzgün yazır.
