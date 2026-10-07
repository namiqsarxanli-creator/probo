# Autonomous Inc. — Research Studio v0.2

Python 3.10+ standart kitabxanası ilə işləyən lokal araşdırma şirkəti.

## Başlatmaq

PyCharm-da `main.py` faylını Run edin və http://127.0.0.1:8812 ünvanını açın.
Port istifadə olunursa ikinci server başlatmayın. Yeni server üçün `PORT` dəyişənini seçin.

## Real AI bağlantısı

`.env.example` faylını `.env` adı ilə kopyalayın. `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` və seçilmiş modelin aktual giriş/çıxış tariflərini daxil edin. Açarı repoya və söhbətə yazmayın. Konfiqurasiya restart olmadan yenidən oxunur.

API HTTPS Chat Completions və JSON object formatını dəstəkləməlidir. Groq nümunə ünvanı `https://api.groq.com/openai/v1`-dir. Tariflər milyon token üçün USD-dir. `0` yalnız həqiqi pulsuz tarif üçün istifadə edilməlidir.

Provayder sənədləri: https://console.groq.com/docs/api-reference və https://console.groq.com/docs/structured-outputs

Konfiqurasiya hazır olsa belə, real bağlantı ilk çağırışda yoxlanır. Açar yoxdursa, real icra başlamır; simulyasiyaya gizli keçid yoxdur.

## İş axını

Yeni sifarişdə «Bazar araşdırması» seçəndə məhsul, region, hədəf müştəri və veriləcək qərar tələb olunur. «Bazar araşdırması» bölməsində tələb, müştəri, rəqiblər, qiymətlər və satış kanalları üçün beş suallıq plan görünür. Real rejimdə hər sual üzrə ayrıca axtarış aparılır (cəmi ən çox 10 mənbə). Axtarışa məhsul və region göndərilir; məqsəd və müştəri məlumatı axtarış xidmətinə göndərilmir.

Təsdiqlənmiş mənbədən sübut cədvəlinə iddia və dəqiq sitat əlavə edin. Məlumatın aid olduğu regionu və tarixini qeyd edin. Sitat mənbədə avtomatik yoxlanır; məna və region uyğunluğunu insan yoxlayır. Tarixi olmayan və bir ildən köhnə məlumat işarələnir. Ziddiyyət qeydi saxlanıla bilər. Cavabı olmayan suallar məlumat boşluğu kimi göstərilir və yekun hesabatda qeyd olunur.

### Müştəri yoxlaması

«Müştəri yoxlaması» bölməsində bir anonim müsahibəni (1 iştirakçı), qrup sorğusunu və ya pilot satış nəticəsini saxlayın. Anonim kod, region, seqment, tarix, iştirakçı seçimi və nəticə qeydi tələb olunur. İştirakçı, problemi bildirən, alış niyyəti bildirən və faktiki ödəniş edən sayları ayrıdır; hər say iştirakçı sayından böyük ola bilməz. Eyni kod təkrar qəbul edilmir. Eyni insanlar müxtəlif qeydlərdə iştirak edə bilər; istifadəçi təkrar saymanı yoxlamalıdır.

Nəticələr növ, region, seqment və seçim üsulu üzrə qruplaşdırılır. Faizlər sayların cəmi üzərindən hesablanır və yalnız qeydə alınmış nümunəyə aiddir. Onlar bütün bazara tətbiq edilmir. Qeydlər AI mesajlarına daxil edilmir; lokal hesabat və audit JSON ixracına daxil edilir. Bu bölmə müştərilərə sorğunu özü göndərmir: əldə etdiyiniz cavabları saxlayır.

### Bazar hesablaması

«Bazar hesablaması» bölməsində regiondakı potensial müştəri sayı, hədəf seqment payı, xidmət göstərə biləcəyiniz pay və müştəri üzrə illik xərc daxil edin. Hər giriş üçün fərziyyə və ya sübut istinadı, eləcə də əsaslandırma tələb olunur. İstinad seçiləndə mənbəsi təsdiqlənmiş sübut tələb olunur; sitatdakı rəqəmin girişə uyğunluğunu insan yoxlayır.

- TAM = müştəri sayı × illik xərc.
- SAM = TAM × hədəf seqment payı × xidmət edilə bilən pay.
- SOM = SAM × əldəetmə payı.

Aşağı, əsas və yuxarı əldəetmə payları üç ssenari yaradır. Əldəetmə müddəti 1–60 aydır; məbləğ həmin miqyasa çatanda illik potensialdır və bu müddətdə yığılmış gəlir deyil. Valyuta AZN, USD və ya EUR-dur; avtomatik məzənnə çevrilməsi yoxdur. Köhnə, tarixi məlum olmayan, ziddiyyətli və sonradan çıxarılmış/rədd edilmiş sübutlar işarələnir. Hesablamalar satış proqnozu və statistik etibar intervalı deyil.

Bu qeydləri qaralama, fasilədə və hesabat baxışı gözləyən sifarişdə dəyişmək olar. Təsdiqlənmiş hesabatda dəyişikliklər qəbul edilmir. Yeni məlumatlar Markdown hesabatı, audit JSON və Hesabatlar ekranına daxil edilir.

1. Yeni sifariş yaradın. Nümayiş rejimi uydurma mənbələri özü əlavə edir.
2. Real sifariş yarananda agent arxa planda mövzu üzrə açıq mənbələr axtarır. «Mənbə qiymətləndirməsi» bölməsində axtarışın vəziyyətini və nəticələrini izləyin. «Öz mənbəmi əlavə et» ilə istədiyiniz HTTPS mənbəsini əlavə edə, «Yenidən mənbə axtar» ilə axtarışı təkrarlaya bilərsiniz. Köhnə sifarişlərdə axtarışı bu düymə ilə başladın.
3. «Mənbə qiymətləndirməsi» bölməsində URL-i və mətni oxuyun, mövzuya uyğunluğa 1–5 bal verin və mənbəni təsdiqləyin və ya rədd edin. Ən azı iki təsdiqlənmiş mənbə olduqdan sonra araşdırmanı başladın. Rədd edilən mənbələr AI kontekstinə daxil edilmir.

Açıq mənbə axtarışına yalnız sifarişin adı göndərilir. Axtarış xülasəsi səhifənin tam mətni deyil; real iş üçün mənbənin özünü yoxlayın.
4. Böhran laboratoriyasında aktiv işçini dayandırıb təhvili izləyin.
5. «Fakt yoxlama» bölməsində hər iddianı sitat və mənbə konteksti ilə müqayisə edib qəbul edin və ya çıxarın. Canlı hesabatın təsdiqi üçün bütün faktlar yoxlanmalı, hər mərhələdə ən azı bir fakt qəbul edilməlidir. «Hesabatlar» bölməsindən düzəliş istəmək mümkündür. Markdown və audit JSON ixracı var.

«İcra və xərclər» bölməsi çağırış vəziyyətini, token istifadəsini, gözləmə hadisələrini və tətbiqin hesabladığı xərci göstərir.

## Keyfiyyət laboratoriyası

«Keyfiyyət laboratoriyası» bölümündə ilk təsdiqlənmiş mənbədən insanın yoxladığı sitatları mərhələlər üzrə golden dataset-ə əlavə edin. Namizədlərin sınaqları həmin ilk mənbə ilə aparıldığı üçün dəst yalnız bu mənbənin sitatlarını qəbul edir. Hər əlavə və ya silmə dataset versiyasını artırır.

«İki profili müqayisə et» əvvəl saxlanmış Iris və Orion sınaq çıxışlarını eyni dəstə qarşı ölçür; yeni AI çağırışı və xərc yaratmır. Precision, recall, F1, xərc, müddət və mərhələ üzrə fərqlər göstərilir. Eksperiment köhnə dataset surəti ilə saxlanılır və JSON şəklində ixrac olunur. 20-dən az nümunə ilə model/prompt seçimi üçün qəti nəticə çıxarmayın.

Bu ölçmə **sitat seçimi** üçündür. Mənbədəki sitatın iddianı mənaca sübut etməsini yoxlamır. Gold dəst bütün düzgün sitatları əhatə etmirsə, ona uyğun gəlməyən çıxış sitatı avtomatik halüsinasiya sayılmır. Fərqli prompt və modellərin yeni çağırışla sınağı bu lokal, xərcsiz müqayisəyə daxil deyil.

## Yeni əməliyyat bölmələri

1. **Maliyyə planı:** ilkin vəsaiti, aylıq yeni müştərini, qiyməti, müştəri üzrə və sabit xərcləri, itki və artım faizlərini daxil edin. Sistem 1–36 ay üçün gəlir, xərc və qalan vəsaiti hesablayıb sifarişdə saxlayır. AI büdcəsi bu plandan ayrıdır.
2. **Ssenarilər:** əsas plan saxlanandan sonra satış və xərc əmsalını, satış gecikməsini dəyişib nəticələri əsas planla müqayisə edin. Ssenari real sifariş büdcəsini dəyişmir.
3. **Tapşırıq və təqvim:** məsul şəxs və son tarixlə iş əlavə edin, vəziyyətini dəyişin, `.ics` faylını təqvim tətbiqinə idxal edin.
4. **Müştəri portalı:** sifariş üçün lokal giriş keçidi yaradın. Ayrı baxışda müştəri gedişi, tapşırıqları və yalnız təsdiqlənmiş hesabatı görür, rəy yaza bilir. Keçid yenilənə və ləğv edilə bilər. Server yalnız `127.0.0.1` üzərində işlədiyi üçün başqa kompüterdən giriş yoxdur.

## Saxlanma

Yeni məlumatlar `data/studio.sqlite3` faylındadır. Əvvəlki `data/company.sqlite3` dəyişdirilmir. Köhnə simulyator `python legacy.py` ilə 8811 portunda açılır. Server yalnız bu kompüterdə işləyir. Bu buraxılış internetə açıq SaaS deyil.

## Məhdudiyyətlər

- Rəhbər qayda əsaslıdır; rollar araşdırmaçı, analitik, redaktordur. Dinamik rol yaratma yoxdur.
- İki namizəd eyni modelin fərqli təlimat profilləridir. Bal format/sitat yoxlamasıdır, ümumi zəka göstəricisi deyil.
- Fakt yoxlama insan qərarıdır; mənbədə tapılan sitat iddianın mənaca düzgün olmasını avtomatik sübut etmir. Rədd edilmiş faktlar hesabatdan çıxarılır. Əvvəlki hazır sifarişlərdə faktlar yenidən baxış gözləyir.
- Sitatın mətndə olması avtomatik yoxlanır. Bir cavabdakı səhv sitatlı iddialar çıxarılır; heç bir etibarlı sitat qalmırsa mərhələ dayanır. İddianın semantik doğruluğunu sahibi qiymətləndirir.
- Açıq mənbə axtarışı mövzu üzrə aparılır; mənbələrin keyfiyyətini və uyğunluğunu istifadəçi yoxlamalıdır. PDF və JS-dən asılı səhifələr üçün mətn əl ilə əlavə edilir.
- Maksimum 10 mənbə, hər biri 16000 simvol. Əsas model kontekstinə mənbənin ilk 8000 simvolu, sınağa ilk mənbənin 3000 simvolu daxil olur.
- Yaddaş təsdiqlənmiş işlərin nəticə qeydləridir; avtomatik model təlimi və gələcək plana yaddaş tətbiqi yoxdur.
- Xərc daxil edilən tariflə hesablanır, provayder fakturası deyil. İstifadə sayı bilinməyən və yarımçıq çağırışların rezervi saxlanılır. Provayder hesabında ayrıca sərf limiti təyin edin.
- Provayder 429 qaytaranda çağırışın rezervi geri qaytarılır, `retry-after` başlığına və ya artan gözləmə müddətinə əsasən sifariş gözləyir və sonra avtomatik davam edir. İstifadəçi gözləmə zamanı sifarişə fasilə verə bilər.
- Maliyyə planı sadə fərziyyə hesablamasıdır; vergi, borc, birdəfəlik xərclər və mühasibat uçotu yoxdur. Nəticə bazar proqnozu deyil.
- Müştəri portalında hesab və rol sistemi yoxdur; keçidi bilən bu kompüterdə baxışı aça bilər. Keçidi məxfi saxlayın. İnternetdən giriş və xarici paylaşım yoxdur.
- Ödəniş qəbulu və monitorinq bu mərhələyə daxil deyil.

## Testlər

`python -m unittest discover -s tests -v`

Testlər xarici AI hesabına sorğu göndərmir. API iş axını idarə olunan test provayderi ilə yoxlanır. Real provayderin keyfiyyəti, kvotası və hesablanması canlı pilotda yoxlanmalıdır.

## Arxitektura

- `app/studio.py`: sifariş, işə qəbul, təhvil, sitat yoxlaması, büdcə, davamlı vəziyyət.
- `app/operations.py`: aylıq maliyyə və ssenari hesablamaları.
- `app/evaluation.py`: saxlanmış sınaq çıxışlarının golden dataset-lə ölçülməsi.
- `app/provider.py`: server konfiqurasiyası və API adapteri.
- `app/sources.py`: HTTPS mənbə idxalı, xüsusi şəbəkə bloklaması.
- `app/studio_server.py`: CSRF/Host yoxlamalı lokal HTTP API və fon icrası.
- `static/studio.*`, `static/studio_modules.*`: lokal idarəetmə paneli.
- `static/studio_eval.*`: keyfiyyət laboratoriyası paneli.
- `static/portal.*`: məhdud müştəri baxışı.
- `app/engine.py`, `app/server.py`: əvvəlki simulyator.
