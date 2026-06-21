import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { NavigationContainer } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { Text } from 'react-native';

import MisPuntosScreen from './src/screens/MisPuntosScreen';
import PideTuCanchaScreen from './src/screens/PideTuCanchaScreen';
import VerificadorScreen from './src/screens/VerificadorScreen';
import { colors } from './src/theme';

const Tab = createBottomTabNavigator();

function icono(emoji: string) {
  return ({ color }: { color: string }) => (
    <Text style={{ fontSize: 20, color }}>{emoji}</Text>
  );
}

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Tab.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colors.pino },
          headerTintColor: colors.lima,
          headerTitleStyle: { fontWeight: '800' },
          tabBarActiveTintColor: colors.pino,
          tabBarInactiveTintColor: colors.tenue,
        }}
      >
        <Tab.Screen name="Pide tu cancha" component={PideTuCanchaScreen}
          options={{ tabBarIcon: icono('📍') }} />
        <Tab.Screen name="Mis puntos" component={MisPuntosScreen}
          options={{ tabBarIcon: icono('⭐') }} />
        <Tab.Screen name="Verificador" component={VerificadorScreen}
          options={{ tabBarIcon: icono('✅') }} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
