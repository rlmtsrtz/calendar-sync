import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:intl/intl.dart';
import 'package:uuid/uuid.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:async';

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
  bool _isUpdating = false;

  Future<void> _triggerUpdate() async {
    setState(() => _isUpdating = true);
    
    // Einfaches Lade-Overlay für 10 Sekunden zur visuellen Rückmeldung
    await Future.delayed(const Duration(seconds: 10));
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Das automatische Update läuft alle 3 Stunden.')),
      );
      setState(() => _isUpdating = false);
    }
  }

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
                String teamId = '';
                if (urlInput.contains('team-id/')) {
                  final part = urlInput.split('team-id/')[1];
                  teamId = part.split(RegExp(r'[/|#|?]'))[0];
                }
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

  Widget _buildKombiCard(String title, String filename, IconData icon) {
    return Card(
      elevation: 2,
      child: ListTile(
        leading: Icon(icon, color: Colors.green),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        trailing: ElevatedButton.icon(
          onPressed: () => _copyToClipboard(_getWebcalUrl(filename), 'Link kopiert!'),
          icon: const Icon(Icons.copy, size: 18),
          label: const Text('Link'),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Scaffold(
          appBar: AppBar(
            title: const Text('TuS Dornberg Kalender Zentrale'),
            backgroundColor: Theme.of(context).colorScheme.primaryContainer,
            actions: [
              IconButton(
                icon: const Icon(Icons.sync),
                tooltip: 'Info',
                onPressed: _isUpdating ? null : _triggerUpdate,
              ),
            ],
          ),
          body: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('KOMBI-LINKS (Alle Mannschaften)', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                _buildKombiCard('Alle Spiele', 'all_teams.ics', Icons.all_inclusive),
                _buildKombiCard('Nur Heimspiele', 'all_teams_home.ics', Icons.home),
                _buildKombiCard('Nur Auswärtsspiele', 'all_teams_away.ics', Icons.flight_takeoff),
                const SizedBox(height: 24),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Deine Mannschaften',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                    ),
                    TextButton.icon(
                      onPressed: _isUpdating ? null : _triggerUpdate,
                      icon: const Icon(Icons.info_outline),
                      label: const Text('Auto-Update: Alle 3h'),
                    ),
                  ],
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
                              children: [
                                Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 16.0),
                                  child: Wrap(
                                    spacing: 8,
                                    children: [
                                      ActionChip(
                                        avatar: const Icon(Icons.copy, size: 16),
                                        label: const Text('Alle'),
                                        onPressed: () => _copyToClipboard(_getWebcalUrl('$teamId.ics'), 'Link kopiert!'),
                                      ),
                                      ActionChip(
                                        avatar: const Icon(Icons.home, size: 16),
                                        label: const Text('Heim'),
                                        onPressed: () => _copyToClipboard(_getWebcalUrl('${teamId}_home.ics'), 'Link kopiert!'),
                                      ),
                                      ActionChip(
                                        avatar: const Icon(Icons.flight_takeoff, size: 16),
                                        label: const Text('Gast'),
                                        onPressed: () => _copyToClipboard(_getWebcalUrl('${teamId}_away.ics'), 'Link kopiert!'),
                                      ),
                                    ],
                                  ),
                                ),
                                if (matches.isEmpty)
                                  const Padding(
                                    padding: EdgeInsets.all(16.0),
                                    child: Text('Noch keine Spieldaten gefunden. Das System prüft alle 3h auf Updates.'),
                                  )
                                else
                                  ...matches.map((m) {
                                    final DateTime date = DateTime.parse(m['start']);
                                    final bool isHome = m['isHome'] ?? false;
                                    return ListTile(
                                      dense: true,
                                      leading: Icon(isHome ? Icons.home : Icons.flight_takeoff, size: 16, color: Colors.grey),
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
                                        label: const Text('Fussball.de'),
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
                                        label: const Text('Löschen', style: TextStyle(color: Colors.red)),
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
                      icon: const Icon(Icons.settings),
                      label: const Text('Logs'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        if (_isUpdating)
          Container(
            color: Colors.black54,
            child: const Center(
              child: Card(
                child: Padding(
                  padding: EdgeInsets.all(24.0),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 20),
                      Text(
                        'Wartungsmodus...',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                      ),
                      SizedBox(height: 10),
                      const Text(
                        'Das System aktualisiert sich alle 3 Stunden automatisch.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
