import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

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
    String id = '';
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Neue Mannschaft hinzufügen'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              decoration: const InputDecoration(labelText: 'Name der Mannschaft (z.B. 1. Mannschaft)'),
              onChanged: (value) => name = value,
            ),
            TextField(
              decoration: const InputDecoration(labelText: 'Fussball.de Team-ID'),
              onChanged: (value) => id = value,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Abbrechen')),
          ElevatedButton(
            onPressed: () async {
              if (name.isNotEmpty && id.isNotEmpty) {
                await _firestore.collection('teams').doc(id).set({
                  'name': name,
                  'id': id,
                  'createdAt': FieldValue.serverTimestamp(),
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
              color: Colors.green.shade50,
              child: ListTile(
                leading: const Icon(Icons.auto_awesome, color: Colors.green),
                title: const Text('Alle Mannschaften in einem Kalender', style: TextStyle(fontWeight: FontWeight.bold)),
                subtitle: const Text('Abonniere diesen Link, um automatisch alle Spiele aller angelegten Teams zu sehen.'),
                trailing: ElevatedButton.icon(
                  onPressed: () => _copyToClipboard(_getWebcalUrl('all_teams.ics'), 'Kombinierter Webcal-Link kopiert!'),
                  icon: const Icon(Icons.copy),
                  label: const Text('Link kopieren'),
                ),
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Einzelne Mannschaften',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: StreamBuilder<QuerySnapshot>(
                stream: _firestore.collection('teams').snapshots(),
                builder: (context, snapshot) {
                  if (snapshot.hasError) return Text('Fehler: ${snapshot.error}');
                  if (snapshot.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator());

                  final teams = snapshot.data!.docs;

                  return ListView.builder(
                    itemCount: teams.length,
                    itemBuilder: (context, index) {
                      final team = teams[index].data() as Map<String, dynamic>;
                      final teamId = team['id'];
                      return Card(
                        child: ListTile(
                          title: Text(team['name'] ?? 'Unbekannt'),
                          subtitle: Text('ID: $teamId'),
                          trailing: IconButton(
                            icon: const Icon(Icons.copy),
                            tooltip: 'Einzel-Link kopieren',
                            onPressed: () => _copyToClipboard(_getWebcalUrl('$teamId.ics'), 'Einzel-Link für ${team['name']} kopiert!'),
                          ),
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
