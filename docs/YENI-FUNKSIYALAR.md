# Təqdimat üçün üç yeni funksiya

## 1. Qərar xəritəsi

Söz və Tender kartlarında **Qərarın yolunu göstər** düyməsini seçin. Müraciət, agent/model, kodla yoxlama, həmkar rəyi və yekun nəticə göstərilir. Sitat düyməsi orijinal sənəddə həmin hissəni işıqlandırır. Vaxt və xərc saxlanmış çağırış qeydindən gəlir; modelin daxili düşüncə mətni göstərilmir.

## 2. Sifariş və stok

**Sifariş və stok → Test sifarişlərini və stoku yüklə.** Məlumatlar yalnız lokal test cədvəllərinə əlavə edilir; yenidən yükləmə istifadə olunmuş stoku bərpa etmir.

Mesaj Agentliyində yazın:

> 48213 nömrəli sifarişim haradadır?

və ya:

> 48213 sifarişini L ölçüsünə dəyişmək istəyirəm.

Agent test sifarişini və stoku lokal alətlə oxuyur. İkinci müraciətdə şərtlər uyğundursa dəyişmə müraciəti hazırlayır. Stok yalnız **Test dəyişməni təsdiqlə və stoku rezerv et** seçildikdən sonra azalır. Hazırlanmış müraciət ayrıca sifariş bölməsində də təsdiqlənə bilər.

- 48213: yaxın tarixli, dəyişmə sınağı üçün uyğundur.
- 48214: 20 gün əvvəl qəbul edilib; avtomatik dəyişmə rədd edilir.
- Hazırlamada stok dəyişmir; təsdiqdə qayda versiyası və stok yenidən yoxlanır.
- Təkrar təsdiq stoku ikinci dəfə azaltmır.
- Alət əməliyyatı agentin AI keyfiyyət balını artırmır.
- Bu adapter real mağaza, real müştəri identifikasiyası və CRM-ə qoşulmayıb. İstehsal üçün həmin bağlantı və müştəri autentifikasiyası ayrıca tələb olunur.

## 3. Şirkətin tenderə uyğunluğu

Tender bölməsində **Nümunəni formaya yaz → Profili saxla → Seçilmiş tenderlə müqayisə et**.

Nümunə tenderdə əvvəlki ilin dövriyyəsi və tarixli oxşar müqavilə qeydləri müqayisə edilir. Vergi arayışı olmadığı üçün nəticə **Məlumat çatışmır** qalır. Dövriyyəni `100 000 AZN` edin, saxlayıb yenidən müqayisə edin: tələb ödənmədiyi göstərilir.

Sübut mətninin dəstəklənən forması:

```text
2025 illik dövriyyə: 600 000 AZN.
2025-05-10 tarixli oxşar müqavilə uğurla icra edilib: Müqavilə A.
2025-09-15 tarixli oxşar müqavilə uğurla icra edilib: Müqavilə B.
```

Hər nəticə tender bəndinə və şirkət sənədinin mətninə bağlıdır. Tanınmayan tələb, yanlış il, qeyri-müəyyən və ya çatışmayan sübut avtomatik uyğun sayılmır. Bu, sənədlər üzrə ilkin müqayisədir; sənədin autentikliyinə, müqavilənin həqiqətən oxşar olmasına və yekun iştirak qərarına zəmanət deyil. Təminat, tarix, lot və digər şərtlər ayrıca yoxlanır.

## İşə salma

PyCharm layihəsinə funksiyalar əlavə edilib. Adi server: `agentlik.py` (standart port 8830).

Bu dəyişikliklərin brauzer yoxlaması ayrıca bazada, deterministik test modeli ilə aparılıb. Hazırda 8830-dakı yoxlama serveri açıq şəkildə **OFLAYN SINAQ** göstərir və heç bir API açarı istifadə etmir. Sınaq çağırışlarındakı xərc və vaxtlar test modelinin nümunə göstəriciləridir, real provayder xərci deyil. Şirkətin canlı bazası sınaqda dəyişdirilməyib.
