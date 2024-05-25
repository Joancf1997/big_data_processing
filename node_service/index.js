require('dotenv').config()
const axios = require('axios');
const { Kafka } = require('kafkajs');
const { InfluxDB } = require('@influxdata/influxdb-client');


// API Configuration
const url = 'https://us-central1-1.gcp.cloud2.influxdata.com'
const token = 'qwt4B_P397mDuNmqfZpjM0uAlTXRi_8aTMfxNhQ9w4PXiVu105F05qXbiptWxlR-K91GILML5qKorELJ7f_MTg=='
const org = 'f61a673ffecc6d9b'
const timeout = 60000
const influxClient = new InfluxDB({ url, token, timeout}).getQueryApi(org);

//  Weather API configuration
// const weatherApiUrl = process.env.weatherApiUrl;

// // Kafka configuration
// const kafkaBroker = process.env.KAFKA_BROKER;
// const kafkaTopic = 'data-topic';
// const kafka = new Kafka({
//   clientId: 'node-service',
//   brokers: [kafkaBroker]
// });
// const producer = kafka.producer();



// ================== Solar Panel Generation
const solarPanelGeneration = async () => {
  const query = `
    from(bucket: "TRINIDAD REU 01")
      |> range(start: -20d)
      |> filter(fn: (r) => r["_measurement"] == "MET01")
      |> filter(fn: (r) => r["ID"] == "MET01")
      |> filter(fn: (r) => r["_field"] == "kW_tot")
      |> aggregateWindow(every: 1s, fn: mean, createEmpty: false)
      |> group(columns: ["_measurement"])
      |> last()
      |> drop(columns: ["_time"])
      |> pivot(rowKey:["_field"], columnKey: ["_measurement"], valueColumn: "_value")
  `;
  
  try {
      return await queryInfluxDBSolar(influxClient, query);
  } catch (error) {
      return []
  }
}
function queryInfluxDBSolar(client, query) {
  return new Promise((resolve, reject) => {
      const r = [];
      
      const fluxObserver = {
          next(row) {
              r.push(row[3]);
          },
          error(error) {
              reject(error);
          },
          complete() {
            resolve({
              timestamp: new Date(),
              solar: r[0]
          });
          }
      };
      client.queryRows(query, fluxObserver);
  });
}



// ================== Hydroelectric Generation
const HydroelectricGeneration = async () => {
  const query = `
    from(bucket: "ERC")
      |> range(start: -30m)
      |> filter(fn: (r) => r["_field"] == "kW_tot")
      |> aggregateWindow(every: 31m, fn: mean, createEmpty: false)
      |> group(columns: ["_measurement"])
      |> last()
      |> drop(columns: ["_time"])
      |> pivot(rowKey:["_field"], columnKey: ["_measurement"], valueColumn: "_value")
  `;
  
  try {
      return await queryInfluxDBHydro(influxClient, query);
  } catch (error) {
      return []
  }
}
function queryInfluxDBHydro(client, query) {
  return new Promise((resolve, reject) => {
      const r = [];
      
      const fluxObserver = {
          next(row) {
            r.push({
              timestamp: new Date(), 
              gen1: row[3], 
              gen2: row[4], 
              gen3: row[5], 
              gen4: row[6], 
              gen5: row[7], 
              gen6: row[8], 
              gen7: row[9], 
              gen8: row[10], 
              gen9: row[11]  
            });
          },
          error(error) {
            reject(error);
          },
          complete() {
            resolve(r[0]);
          }
      };
      client.queryRows(query, fluxObserver);
  });
}


// ================== Energy consumption - Mall
const MallEnergyConsumption = async () => {
  const query = `
    from(bucket: "TIERRA AZUL")
      |> range(start: -1d)
      |> filter(fn: (r) => r["_field"] == "kw_tot")
      |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
      |> group(columns: ["_measurement"])
      |> last()
      |> drop(columns: ["_time"])
      |> pivot(rowKey:["_field"], columnKey: ["_measurement"], valueColumn: "_value")
  `;
  
  try {
      return await queryInfluxDBMall(influxClient, query);
  } catch (error) {
      return []
  }
}
function queryInfluxDBMall(client, query) {
  return new Promise((resolve, reject) => {
      const r = [];
      
      const fluxObserver = {
          next(row) {
            r.push({
              timestamp: new Date(), 
              con1: row[3], 
              con2: row[4], 
              con3: row[5], 
              con4: row[6], 
              con5: row[7], 
              con6: row[8], 
              con7: row[9], 
              con8: row[10], 
              con9: row[11], 
              con10: row[12], 
              con11: row[13], 
              con12: row[14], 
              con13: row[15], 
              con14: row[16], 
              con15: row[17], 
              con16: row[18], 
              con17: row[19], 
              con18: row[20] 
            });
          },
          error(error) {
            reject(error);
          },
          complete() {
            resolve(r[0]);
          }
      };
      client.queryRows(query, fluxObserver);
  });
}


// ================== Weather conditions on the sited
// Solar panel Energy generation - Huehuetenango/Guatemala 
const fetchWeatherDataSolarPower = async () => {
  try {
    const response = await axios.get("https://api.openweathermap.org/data/2.5/onecall?lat=14.53611&lon=-91.67778&appid=b0941dea317734e2ce97e02fd8782f8c&units=metric");
    let data = {
      zone: "HUE",
      timestamp: new Date(),
      ...response.data.current
    }
    delete data.weather;
    return data;
  } catch (error) {
    console.error('Error fetching weather data:', error);
    return null;
  }
};

// Hydroelectric Energy generation Alta Verapz/Guatemala
const fetchWeatherDataHydroelectric = async () => {
  try {
    const response = await axios.get("https://api.openweathermap.org/data/2.5/onecall?lat=15.5&lon=-90.333333&appid=b0941dea317734e2ce97e02fd8782f8c&units=metric");
    let data = {
      zone: "ALT",
      timestamp: new Date(),
      ...response.data.current
    }
    delete data.weather;
    return data;
  } catch (error) {
    console.error('Error fetching weather data:', error);
    return null;
  }
};

//Mall Energy consumption  Zacapa/Guatemala
const fetchWeatherDataMall = async () => {
  try {
    const response = await axios.get("https://api.openweathermap.org/data/2.5/onecall?lat=14.97222&lon=-89.53056&appid=b0941dea317734e2ce97e02fd8782f8c&units=metric");
    let data = {
      zone: "ZAC",
      timestamp: new Date(),
      ...response.data.current
    }
    delete data.weather;
    return data;
  } catch (error) {
    console.error('Error fetching weather data:', error);
    return null;
  }
};


const sendToKafka = async (data) => {
  await producer.connect();
  await producer.send({
    topic: kafkaTopic,
    messages: [{ value: JSON.stringify(data) }]
  });
  await producer.disconnect();
};

const processData = async () => {
    const influxDataGenSolar = await solarPanelGeneration();
    const influxDataGenHydro = await HydroelectricGeneration();
    const influxDataConsumption = await MallEnergyConsumption();
    const solarPowerWeather = await fetchWeatherDataSolarPower();
    const hydroelectricWeather = await fetchWeatherDataHydroelectric();
    const mallWeather = await fetchWeatherDataMall();
    console.log(influxDataGenSolar)
    console.log(solarPowerWeather)
    console.log(influxDataGenHydro)
    console.log(hydroelectricWeather)
    console.log(influxDataConsumption)
    console.log(mallWeather)

//   if (influxData && weatherData) {
//     const combinedData = { influxData, weatherData };
//     await sendToKafka(combinedData);
//   }
};

// setInterval(processData, 6000); // Fetch and send data every 60 seconds

processData()
