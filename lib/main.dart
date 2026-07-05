import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:intl/intl.dart';
import 'package:uuid/uuid.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: const FirebaseOptions(
      apiKey: "AIzaSyAPeEpxsaqPi8s0ByBFK7Sam_D_F13KCrs",
      authDomain: "tus-dornberg-calendar.firebaseapp.com",
      projectId: "tus-dornberg-calendar",
      storageBucket: "tus-dornberg-calendar.firebasestorage.app",
      messagingSenderId: "275335490729",
      appId: "1:275335490729:web:bfe85fbb296d3056e84db8",
      measurementId: "G-2LTSN8KVVK",
    ),
  );
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TuS Dornberg Kalender',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: const CalendarDashboard(),
    );
  }
}

class CalendarDashboard extends StatefulWidget {
  const CalendarDashboard({super.key});

  @override
  State<CalendarDashboard> createState() => _CalendarDashboardState();
}

class _CalendarDashboardState extends State<CalendarDashboard> {
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;

  String _getWebcalUrl(String filename) {
    final baseUrl = Uri.base.toString().split('#')[0];
    final host = Uri.parse(baseUrl).host;
    final path = Uri.parse(baseUrl).path;
    return 'webcal://$host${path}calendars/$filename';
  }

  void _copyToClipboard(String text, String message) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  void _addTeamDialog() {
    String name = '';
    String urlInput = '';
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Neue Mannschaft hinzufügen'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              decoration: const InputDecoration(
                labelText: 'Name der Mannschaft',
                hintText: 'z.B. TuS Dornberg 1.',
              ),
              onChanged: (value) => name = value,
            ),
            const SizedBox(height: 10),
            TextField(
              decoration: const InputDecoration(
                labelText: 'Fussball.de Link',
                hintText: 'Kopiere die ganze Adresse hier rein',
              ),
              onChanged: (value) => urlInput = value,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Abbrechen')),
          ElevatedButton(
            onPressed: () async {
              if (name.isNotEmpty && urlInput.isNotEmpty) {
                // Team-ID extrahieren für den Scraper
                String teamId = '';
                if (urlInput.contains('team-id/')) {
                  final part = urlInput.split('team-id/')[1];
                  teamId = part.split(RegExp(r'[/|#|?]'))[0];
                }
                
                // Wir nutzen eine neue UUID für das Dokument, damit nichts überschrieben wird
                final String docId = const Uuid().v4();
                
                await _firestore.collection('teams').doc(docId).set({
                  'name': name,
                  'url': urlInput,
                  'id': teamId,
                  'createdAt': FieldValue.serverTimestamp(),
                  'lastMatches': [],
                });
                Navigator.pop(context);
              }
            },
            child: const Text('Speichern'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('TuS Dornberg Kalender Zentrale'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              elevation: 4,
              color: Colors.green.shade50,
              child: ListTile(
                leading: const Icon(Icons.auto_awesome, color: Colors.green, size: 40),
                title: const Text('KOMBI-LINK: Alle Teams abonnieren', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                subtitle: const Text('Nutze diesen Link in Google Kalender (via URL hinzufügen).'),
                trailing: ElevatedButton.icon(
                  onPressed: () => _copyToClipboard(_getWebcalUrl('all_teams.ics'), 'Kombinierter Webcal-Link kopiert!'),
                  icon: const Icon(Icons.copy),
                  label: const Text('Link kopieren'),
                ),
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Deine Mannschaften',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: StreamBuilder<QuerySnapshot>(
                stream: _firestore.collection('teams').orderBy('createdAt', descending: true).snapshots(),
                builder: (context, snapshot) {
                  if (snapshot.hasError) return Text('Fehler: ${snapshot.error}');
                  if (snapshot.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator());

                  final teams = snapshot.data!.docs;

                  if (teams.isEmpty) {
                    return const Center(child: Text('Noch keine Mannschaften angelegt.'));
                  }

                  return ListView.builder(
                    itemCount: teams.length,
                    itemBuilder: (context, index) {
                      final teamDoc = teams[index];
                      final team = teamDoc.data() as Map<String, dynamic>;
                      final teamId = team['id'] ?? 'Keine ID';
                      final List matches = team['lastMatches'] ?? [];

                      return Card(
                        child: ExpansionTile(
                          title: Text(team['name'] ?? 'Unbekannt', style: const TextStyle(fontWeight: FontWeight.bold)),
                          subtitle: Text('ID: $teamId'),
                          trailing: IconButton(
                            icon: const Icon(Icons.copy),
                            tooltip: 'Einzel-Link kopieren',
                            onPressed: () => _copyToClipboard(_getWebcalUrl('$teamId.ics'), 'Einzel-Link kopiert!'),
                          ),
                          children: [
                            if (matches.isEmpty)
                              const Padding(
                                padding: EdgeInsets.all(16.0),
                                child: Text('Noch keine Spieldaten gefunden. Starte den Scraper auf GitHub.'),
                              )
                            else
                              ...matches.map((m) {
                                final DateTime date = DateTime.parse(m['start']);
                                return ListTile(
                                  dense: true,
                                  leading: const Icon(Icons.event, size: 20),
                                  title: Text(m['summary']),
                                  subtitle: Text(DateFormat('dd.MM.yyyy HH:mm').format(date)),
                                );
                              }).toList(),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  TextButton.icon(
                                    onPressed: () => launchUrl(Uri.parse(team['url'] ?? '')),
                                    icon: const Icon(Icons.link),
                                    label: const Text('Auf Fussball.de öffnen'),
                                  ),
                                  TextButton.icon(
                                    onPressed: () async {
                                      if (await showDialog(
                                        context: context,
                                        builder: (context) => AlertDialog(
                                          title: const Text('Mannschaft löschen?'),
                                          actions: [
                                            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Abbrechen')),
                                            TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Löschen')),
                                          ],
                                        ),
                                      )) {
                                        await teamDoc.reference.delete();
                                      }
                                    },
                                    icon: const Icon(Icons.delete, color: Colors.red),
                                    label: const Text('Entfernen', style: TextStyle(color: Colors.red)),
                                  ),
                                ],
                              ),
                            )
                          ],
                        ),
                      );
                    },
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                ElevatedButton.icon(
                  onPressed: _addTeamDialog,
                  icon: const Icon(Icons.add),
                  label: const Text('Mannschaft hinzufügen'),
                ),
                const Spacer(),
                TextButton.icon(
                  onPressed: () => launchUrl(Uri.parse('https://github.com/rlmtsrtz/calendar-sync/actions')),
                  icon: const Icon(Icons.refresh),
                  label: const Text('Update Status prüfen'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
