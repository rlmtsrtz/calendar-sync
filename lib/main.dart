import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
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
      title: 'Fussball.de Calendar Generator',
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
              decoration: const InputDecoration(labelText: 'Name der Mannschaft'),
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
        title: const Text('Fussball.de Kalender'),
        backgroundColor: Theme.of(context).colorScheme.primaryContainer,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Mannschaften in der Datenbank',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
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
                      return Card(
                        child: ListTile(
                          title: Text(team['name'] ?? 'Unbekannt'),
                          subtitle: Text('ID: ${team['id']}'),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                icon: const Icon(Icons.copy),
                                tooltip: 'Webcal Link kopieren',
                                onPressed: () {
                                  final baseUrl = Uri.base.toString().split('#')[0];
                                  final webcalUrl = 'webcal://${Uri.parse(baseUrl).host}${Uri.parse(baseUrl).path}calendars/${team['id']}.ics';
                                  Clipboard.setData(ClipboardData(text: webcalUrl));
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(content: Text('Webcal-Link kopiert!')),
                                  );
                                },
                              ),
                              IconButton(
                                icon: const Icon(Icons.download),
                                tooltip: 'ICS herunterladen',
                                onPressed: () async {
                                  final baseUrl = Uri.base.toString().split('#')[0];
                                  final url = Uri.parse('${baseUrl}calendars/${team['id']}.ics');
                                  if (await canLaunchUrl(url)) {
                                    await launchUrl(url, mode: LaunchMode.externalApplication);
                                  }
                                },
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: _addTeamDialog,
              icon: const Icon(Icons.add),
              label: const Text('Mannschaft hinzufügen'),
            ),
          ],
        ),
      ),
    );
  }
}
