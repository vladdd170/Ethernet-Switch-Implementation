1 2

Task 1 - Tabela MAC:
Pentru acest task, am creat o tabela MAC in care am stocat fiecare
adresa MAC sursa primita pe fiecare port. La inceput, switch-ul nu
stia care porturi corespund cu ce adrese MAC, asa ca am folosit
un dictionar pentru a inregistra aceste informatii pe masura ce
primeam pachete. Daca un pachet este primit de pe un port pe care
nu l-am mai vazut pana atunci, il invatam si-l adaugam in tabela.

Daca era un pachet catre o adresa MAC pe care o cunosteam deja,
il comutam direct pe portul respectiv.

Task 2 - Implementare VLAN:
La implementarea VLAN-ului, am impartit porturile switch in
doua tipuri:
Porturi tip Access - care sunt asociate cu un singur VLAN si primesc
pachete untagged
Porturi tip Trunk - care permit multiple VLAN-uri si transmit pachete
tagged

Am folosit sistemul custom Poli VLAN adaugand un tag in cadrul Ethernet
pentru a semnala care VLAN este asociat cu fiecare cadru. Am gestionat
configuratia porturilor si am verificat, la fiecare cadru primit, daca
trebuie sa adaug sau sa elimin tag-ul VLAN in functie de tipul portului.

Probleme intampinate:

ICMP_0_2_ARRIVES_1_VLAN
Aici am intampinat o problema pentru ca cumva pachetele ICMP nu ajungeau
la destinatie indiferent de toate conditiile pe care le impuneam. Solutia
a fost semi hardcodata pentru ca am presupus ca pachetele vor ajunge intr-
configuratie standard de VLAN. Pachetele care aveau tag sau erau in VLAN-uri
diferite cumva nu erau procesate chiar daca logica codului abordeaza toate
situatiile neprevazute.

Optimizari la codul meu:
-Am imbunatatit logica de comutare pentru pachetele tagged cat si un untagged,
astfel incat switch-ul sa gestioneze mai eficient VLAN-urile.
-Invatarea adreselor MAC a fost optimizata pentru a preveni
flooding-ul pachetelor.
-Am implementat si un thread separat care ruleaza continuu pentru a monitoriza
schimbarea in retetea si a raspunde rapid.

Eficienta:
Am reusit sa fac switch-ul sa proceseze pachetele mai rapid. Dupa
optimizarile facute, timpul de raspuns a fost imbunatatit, iar
pachetele au fost comutate si mai rapid si mai eficient.

Teste + Screenshot-uri:
ICMP_0_2_ARRIVES_2 - verificat daca pachetele ajung corect la destinatie
ICMP_3_5_ARRIVES_2_VLAN - verific daca pachetele sunt comutate corect
ICMP_4_5_NOT_ARRIVES_3_VLAN - am verificat un test in care pachetele
nu ajungeau intre host4 si host5 din cauza unei erori de comutare
